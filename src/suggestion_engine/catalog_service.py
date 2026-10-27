"""Enriquecimento determinístico de um snapshot formal inteiro (plano §7.1, §8).

Para cada par elemento/requisito do snapshot produz exatamente um
``FieldEnrichmentResult`` — proposto, abstido, não suportado, falho ou não
solicitado —, nunca omitido porque outro campo falhou. Catálogo inválido ou
indisponível não apaga o diagnóstico formal: campos ``non_compliant`` ficam
``failed/package_error``; sem catálogo fixado (``not_attached``) ficam
``abstained/insufficient_context``.
O serviço não chama LLM, HTTP, writer, registry semântico legado nem cache legado; o
leitor de observações é o da mesma sessão/análise do snapshot.
"""

import uuid

from src.domain_catalog.reader import CatalogReader
from src.ifc_analyzer.observations import ObservationReader
from src.operations.contracts import canonical_sha256
from src.suggestion_engine.catalog_context import build_field_context
from src.suggestion_engine.catalog_contracts import (
    ContextRecipe,
    EnrichmentIdentity,
    EnrichmentProblem,
    EnrichmentRun,
    FieldEnrichmentResult,
    FieldEvidenceContext,
    FieldRef,
    M3Reason,
    recipe_for,
)
from src.suggestion_engine.catalog_evidence import assess_evidence
from src.suggestion_engine.catalog_operations import E3OperationBundle, execute_catalog_operation
from src.validation.analysis_service import CatalogUnavailable
from src.validation.diagnostic_models import DiagnosticSnapshot, RequirementResult

_FORMAL: dict[str, tuple[str, M3Reason]] = {
    "compliant": ("not_requested", "already_satisfied"),
    "not_applicable": ("not_requested", "not_applicable"),
    "not_verified": ("unsupported", "formal_not_verified"),
    "error": ("failed", "formal_error"),
}


def enrichment_identity(
    snapshot: DiagnosticSnapshot,
    bundle: E3OperationBundle,
    recipe: ContextRecipe,
    enrichment_id: uuid.UUID,
) -> EnrichmentIdentity:
    """Identidade do run M3 sobre a análise e o diagnóstico exatos."""
    identity = snapshot.identity
    body = {
        "schema_version": 1,
        "analysis_id": str(identity.analysis_id),
        "analysis_identity_sha256": identity.digest(),
        "diagnostic_sha256": snapshot.content_sha256,
        "condition_id": identity.condition_id,
        "condition_config_sha256": identity.condition_config_sha256,
        "recipe_sha256": recipe.digest(),
        "operation_bundle_sha256": bundle.manifest_sha256,
        "builder_version": "1.0.0",
        "catalog": None
        if identity.catalog_ref is None
        else identity.catalog_ref.model_dump(mode="json"),
        "pin_revision": identity.pin_revision,
        "runtime": "deterministic",
    }
    return EnrichmentIdentity.model_validate(
        {**body, "enrichment_id": str(enrichment_id), "input_sha256": canonical_sha256(body)}
    )


def _field(snapshot: DiagnosticSnapshot, row: RequirementResult) -> FieldRef:
    assert row.element is not None
    expected = snapshot.expected_for(row)
    return FieldRef(
        analysis_id=snapshot.identity.analysis_id,
        analysis_identity_sha256=snapshot.identity.digest(),
        snapshot_id=snapshot.snapshot_id,
        diagnostic_sha256=snapshot.content_sha256,
        element=row.element,
        requirement=row.requirement,
        target_set_name=None if expected.set_name is None else expected.set_name.text,
        target_field_name=None if expected.field_name is None else expected.field_name.text,
    )


def _plain(
    field: FieldRef, status: str, reason: M3Reason, *limitations: str
) -> FieldEnrichmentResult:
    return FieldEnrichmentResult(
        field=field,
        context_sha256=None,
        assessment=None,
        status=status,  # type: ignore[arg-type]
        reason=reason,
        reasons=(reason,),
        limitations=limitations,
    )


class CatalogEnrichmentService:
    """Executa contexto → avaliação → operação para todos os campos de um snapshot."""

    def __init__(self, bundle: E3OperationBundle, recipe: ContextRecipe | None = None) -> None:
        """Bundle explícito; a receita vem dos limites congelados do snapshot.

        ``recipe`` explícita só é aceita se for idêntica à derivada desses limites.
        """
        self._bundle = bundle
        self._recipe = recipe

    def enrich(
        self,
        snapshot: DiagnosticSnapshot,
        *,
        observations: ObservationReader,
        catalog: CatalogReader | CatalogUnavailable,
        enrichment_id: uuid.UUID,
    ) -> EnrichmentRun:
        """Run M3 completo; falha técnica de um campo vira resultado ``failed``."""
        recipe = recipe_for(snapshot.identity.limits)
        if self._recipe is not None and self._recipe != recipe:
            raise ValueError("receita difere dos limites congelados na análise (E3-07)")
        results: list[FieldEnrichmentResult] = []
        contexts: list[FieldEvidenceContext] = []
        problems: list[EnrichmentProblem] = []
        for row in snapshot.requirements:
            if row.element is None:
                continue
            field = _field(snapshot, row)
            if isinstance(catalog, CatalogUnavailable):
                # Sem pin não há pacote a falhar: falta contexto cadastral (§7.4).
                missing: tuple[str, M3Reason] = (
                    ("abstained", "insufficient_context")
                    if catalog.state == "not_attached"
                    else ("failed", "package_error")
                )
                status, reason = _FORMAL.get(row.state, missing)
                results.append(_plain(field, status, reason, f"catálogo {catalog.state}"))
                continue
            try:
                context = build_field_context(snapshot, row, catalog, observations, recipe)
                assessment = assess_evidence(context, self._bundle)
                result = execute_catalog_operation(context, assessment, self._bundle)
                contexts.append(context)
            except Exception as exc:  # falha técnica do campo; os demais seguem
                problems.append(
                    EnrichmentProblem(
                        code="internal_error",
                        message=f"{type(exc).__name__}: {exc}",
                        requirement_key=row.requirement.key(),
                        element_express_id=row.element.express_id,
                    )
                )
                result = _plain(field, "failed", "internal_error")
            results.append(result)
        identity = enrichment_identity(snapshot, self._bundle, recipe, enrichment_id)
        body = {
            "schema_version": 1,
            "identity": identity.model_dump(mode="json"),
            "state": "completed",
            "results": [r.model_dump(mode="json") for r in results],
            "contexts": [c.model_dump(mode="json") for c in contexts],
            "problems": [p.model_dump(mode="json") for p in problems],
        }
        return EnrichmentRun.model_validate({**body, "content_sha256": canonical_sha256(body)})
