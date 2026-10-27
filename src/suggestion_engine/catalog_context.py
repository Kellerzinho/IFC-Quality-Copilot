"""Contexto de evidência de um campo (plano §7.1–§7.2, passos 1–5).

Só para resultado formal ``non_compliant`` de propriedade: projeção rica E3.1 do
requisito literal, seletores literais limitados (alvo IDS, caminho canônico do
binding e aliases aprovados de finalidade de resolução, alvo e escopo compatíveis),
busca nos canais P/T da política e nova resolução de **cada caminho observado** no
mesmo release. Limites de seletores, observações (total do campo) e bytes vêm da
receita; excedidos, o contexto é indisponível, sem truncar. Alias de busca/tradução
não habilita evidência; sem conjuntos
explícitos, só o conjunto do binding é buscado, nunca todos os Psets do arquivo.
Falhas previstas viram indisponibilidade tipada; erro inesperado propaga.
"""

from typing import Any, Final

from src.domain_catalog.adapters import build_catalog_projection
from src.domain_catalog.canonical import canonical_json_bytes
from src.domain_catalog.contracts import RESOLVED_STATUSES, BindingRequest
from src.domain_catalog.errors import CatalogPackageError, CatalogProjectionError
from src.domain_catalog.models import RESOLUTION_ALIAS_PURPOSES, AliasMapping, IFCBinding
from src.domain_catalog.projection_contracts import CatalogProjection, ProjectionScope
from src.domain_catalog.reader import CatalogReader
from src.ifc_analyzer.observations import (
    ObservationReader,
    ObservationRefused,
    ScopeName,
    build_search_plan,
)
from src.ifc_analyzer.read_only import IfcSourceError
from src.suggestion_engine.catalog_contracts import (
    ContextRecipe,
    FieldEvidenceContext,
    FieldRef,
    M3Reason,
    ObservedResolution,
    context_digest,
)
from src.validation.diagnostic_models import DiagnosticSnapshot, RequirementResult

CHANNEL_SCOPES: Final[dict[str, ScopeName]] = {"P": "occurrence", "T": "type"}
_PROJECTION_REASONS: Final[dict[str, M3Reason]] = {
    "release_mismatch": "identity_mismatch",
    "insufficient_context": "insufficient_context",
    "foreign_reference": "foreign_reference",
}
_RESOLUTION_REASONS: Final[dict[str, M3Reason]] = {
    "unmapped": "unmapped",
    "ambiguous": "ambiguous_mapping",
    "unsupported": "unsupported_schema",
    "package_error": "package_error",
}


def _alias_selectors(
    reader: CatalogReader, binding: IFCBinding, schema: str, entity: str
) -> list[tuple[str, str, str]]:
    selectors: list[tuple[str, str, str]] = []
    aliases: tuple[AliasMapping, ...] = reader.content.aliases
    for alias in sorted(aliases, key=lambda item: item.id):
        if alias.lifecycle != "approved" or alias.purpose not in RESOLUTION_ALIAS_PURPOSES:
            continue
        if alias.target_binding_id != binding.id:
            continue
        scope = alias.scope
        if scope.schemas is not None and schema not in scope.schemas:
            continue
        if scope.entity_classes is not None and entity.upper() not in {
            name.upper() for name in scope.entity_classes
        }:
            continue
        assert binding.set_name is not None
        for set_name in scope.set_names or (binding.set_name,):
            selectors.append((set_name, alias.term, f"alias:{alias.id}"))
    return selectors


def _context(**data: Any) -> FieldEvidenceContext:
    document = FieldEvidenceContext.model_construct(**data).model_dump(mode="json")
    return FieldEvidenceContext.model_validate(
        {**document, "context_sha256": context_digest(document)}
    )


def build_field_context(
    snapshot: DiagnosticSnapshot,
    result: RequirementResult,
    reader: CatalogReader,
    observations: ObservationReader,
    recipe: ContextRecipe,
) -> FieldEvidenceContext:
    """Contexto de evidência do campo; nunca altera o resultado formal."""
    assert result.element is not None
    identity = snapshot.identity
    expected = next(
        (e for e in snapshot.expected_fields if e.requirement.key() == result.requirement.key()),
        None,
    )
    if expected is None:
        raise ValueError("requisito da linha não pertence ao snapshot (referência estrangeira)")
    field = FieldRef(
        analysis_id=identity.analysis_id,
        analysis_identity_sha256=identity.digest(),
        snapshot_id=snapshot.snapshot_id,
        diagnostic_sha256=snapshot.content_sha256,
        element=result.element,
        requirement=result.requirement,
        target_set_name=None if expected.set_name is None else expected.set_name.text,
        target_field_name=None if expected.field_name is None else expected.field_name.text,
    )
    base: dict[str, Any] = {
        "field": field,
        "formal_state": result.state,
        "formal_reason": result.reason,
        "expected": expected,
        "verifier": identity.verifier,
        "catalog": reader.ref,
        "recipe": recipe,
        "context_sha256": "0" * 64,
    }
    if result not in snapshot.requirements:
        return _context(
            **base,
            unavailable_reason="foreign_reference",
            unavailable_detail="linha de outro snapshot",
        )
    if result.state != "non_compliant":
        return _context(**base)
    if identity.catalog_ref is not None and reader.ref != identity.catalog_ref:
        return _context(
            **base,
            unavailable_reason="identity_mismatch",
            unavailable_detail="reader de outro release",
        )
    request = BindingRequest(
        ifc_schema=snapshot.ifc_schema,  # type: ignore[arg-type]
        facet="property",
        set_name=field.target_set_name,
        field_name=field.target_field_name or "",
        entity=result.element.ifc_class,
        predefined_type=snapshot.context_for(result.element),
        requirement_ref=result.requirement.key(),
    )
    try:
        projection: CatalogProjection = build_catalog_projection(
            reader, ProjectionScope(catalog=reader.ref, request=request)
        )
    except CatalogProjectionError as exc:
        reason: M3Reason = _PROJECTION_REASONS.get(exc.reason, "insufficient_context")
        if exc.reason == "unresolved_binding" and exc.resolution is not None:
            reason = _RESOLUTION_REASONS.get(exc.resolution.status, "unmapped")
        return _context(**base, unavailable_reason=reason, unavailable_detail=str(exc))
    except CatalogPackageError as exc:
        return _context(**base, unavailable_reason="package_error", unavailable_detail=str(exc))
    binding = projection.binding
    field = field.model_copy(update={"binding_id": binding.id, "concept_id": projection.concept.id})
    base = {**base, "field": field, "projection": projection}
    policy = projection.evidence_policy
    if policy is None:
        return _context(**base)
    scopes = tuple(
        CHANNEL_SCOPES[c]
        for c in policy.admissible_channels
        if c in CHANNEL_SCOPES and c in recipe.supported_channels
    )
    if not scopes:
        return _context(**base)
    selectors = [
        (
            field.target_set_name or "",
            field.target_field_name or "",
            f"ids:{result.requirement.key()}",
        ),
        (binding.set_name or "", binding.field_name, f"binding:{binding.id}"),
        *_alias_selectors(reader, binding, snapshot.ifc_schema, result.element.ifc_class),
    ]
    try:
        plan = build_search_plan(
            identity.analysis_id,
            result.element,
            selectors,
            scopes,
            max_selectors=recipe.limits.max_selectors,
        )
        report = observations.read(plan)
    except ObservationRefused as exc:
        return _context(**base, unavailable_reason=exc.reason, unavailable_detail=str(exc))
    except IfcSourceError as exc:
        return _context(**base, unavailable_reason="integrity_error", unavailable_detail=str(exc))
    if len(report.observations) > recipe.limits.max_observations:
        # Total por campo, somando seletores e canais; nunca truncado (E3-07).
        return _context(
            **base,
            unavailable_reason="context_limit_exceeded",
            unavailable_detail=(
                f"{len(report.observations)} observações excedem "
                f"{recipe.limits.max_observations} por campo"
            ),
        )
    resolutions = []
    for observation in report.observations:
        observed = BindingRequest(
            ifc_schema=snapshot.ifc_schema,  # type: ignore[arg-type]
            facet="property",
            set_name=observation.set_name,
            field_name=observation.field_name,
            entity=result.element.ifc_class,
            predefined_type=snapshot.context_for(result.element),
            requirement_ref=result.requirement.key(),
        )
        resolution = reader.resolve_binding(observed)
        admissible = resolution.status in RESOLVED_STATUSES and (
            resolution.binding_id,
            resolution.concept_id,
        ) == (binding.id, binding.concept_id)
        resolutions.append(
            ObservedResolution(
                observation_id=observation.observation_id,
                request=observed,
                resolution=resolution,
                admissible=admissible,
                rejection_reason=None if admissible else "observed_mapping_mismatch",
                alias_ids=resolution.alias_ids,
                decision_ids=resolution.decision_ids,
            )
        )
    context = _context(
        **base, search_plan=plan, search_report=report, resolutions=tuple(resolutions)
    )
    size = len(canonical_json_bytes(context.model_dump(mode="json")))
    if size > recipe.limits.max_context_bytes:
        return _context(
            **base,
            unavailable_reason="context_limit_exceeded",
            unavailable_detail=(
                f"contexto com {size} bytes excede {recipe.limits.max_context_bytes}"
            ),
        )
    return context
