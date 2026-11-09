"""Cache exato de contexto/resultado M3 na tabela ``context_cache`` da autoridade (§8).

Chave SHA-256 completa no namespace ``m1-e3-evidence-v1/cache-v1`` sobre identidade
(projeto/par/revisão/análise/fontes), diagnóstico, elemento/requisito/alvo, release e
pin, hash do contexto (projeção, política, enum, unidade, aliases/decisões, plano,
relatório, observações admitidas e rejeitadas, receita), bundle/handlers, versões de
construtor/avaliação/schema, limites e condição. Todos os componentes ficam no
payload persistido. O resultado tem de ser do mesmo campo/análise/diagnóstico/contexto
dos componentes, e análise, snapshot e run M3 com esse contexto têm de existir na
autoridade (``put`` e ``get``): transplante re-hasheado é ``CacheIntegrityError``. Hit
revalida DTO, hash e chave; mesma chave com outro payload é ``CacheCollisionError``.
Invalidação é lógica: análise nova nunca encontra entradas de outra análise.
"""

from dataclasses import dataclass
from typing import Any, Final, Self

from pydantic import ValidationError, model_validator

from src.domain_catalog.contracts import ContractModel
from src.domain_catalog.models import Sha256Hex
from src.operations.contracts import CanonicalUUID, SchemaVersionOne, canonical_sha256
from src.operations.database import OperationalUnitOfWork
from src.suggestion_engine.catalog_contracts import (
    ASSESSMENT_VERSION,
    BUILDER_VERSION,
    EnrichmentRun,
    FieldEnrichmentResult,
    FieldEvidenceContext,
)
from src.suggestion_engine.catalog_operations import AUTHORIZED_HANDLERS, E3OperationBundle
from src.validation.diagnostic_models import DiagnosticSnapshot

NAMESPACE: Final = "m1-e3-evidence-v1/cache-v1"


class CacheIntegrityError(Exception):
    """Entrada de cache adulterada ou incoerente; nunca é reutilizada."""

    code = "cache_integrity_error"


class CacheCollisionError(Exception):
    """Mesma chave com payload diferente; nada é sobrescrito."""

    code = "cache_collision"


@dataclass(frozen=True)
class _StoredBundle:
    """Vista do bundle registrada no run gravado (manifesto e mapa fechado da condição)."""

    manifest_sha256: str
    handlers: Any


def cache_components(
    snapshot: DiagnosticSnapshot,
    context: FieldEvidenceContext,
    bundle: E3OperationBundle | _StoredBundle,
) -> dict[str, Any]:
    """Componentes resolvíveis da chave (JSON canônico, tipos preservados)."""
    identity = snapshot.identity
    report = context.search_report
    return {
        "namespace": NAMESPACE,
        "project_id": str(identity.project_id),
        "pair_id": str(identity.pair_id),
        "pair_revision": identity.pair_revision,
        "analysis_id": str(identity.analysis_id),
        "ifc": identity.ifc.model_dump(mode="json"),
        "ids": identity.ids.model_dump(mode="json"),
        "analysis_identity_sha256": identity.digest(),
        "diagnostic_sha256": snapshot.content_sha256,
        "element": context.field.element.model_dump(mode="json"),
        "requirement": context.field.requirement.key(),
        "target": [context.field.target_set_name, context.field.target_field_name],
        "expected_sha256": context.expected.digest(),
        "catalog": None if context.catalog is None else context.catalog.model_dump(mode="json"),
        "pin_revision": identity.pin_revision,
        "projection_sha256": None
        if context.projection is None
        else canonical_sha256(context.projection.model_dump(mode="json")),
        "search_plan_sha256": None if report is None else report.plan_sha256,
        "search_report_sha256": None if report is None else report.report_sha256,
        "admissible_observation_ids": sorted(
            r.observation_id for r in context.resolutions if r.admissible
        ),
        "rejected_observation_ids": sorted(
            r.observation_id for r in context.resolutions if not r.admissible
        ),
        "context_sha256": context.context_sha256,
        "recipe_sha256": context.recipe.digest(),
        "operation_bundle_sha256": bundle.manifest_sha256,
        "handlers": sorted(f"{op}@{version}" for op, version in bundle.handlers),
        "builder_version": BUILDER_VERSION,
        "assessment_version": ASSESSMENT_VERSION,
        "schema_version": 1,
        "limits": identity.limits.model_dump(mode="json"),
        "condition_id": identity.condition_id,
        "condition_config_sha256": identity.condition_config_sha256,
        "runtime": "deterministic",
    }


def cache_key(components: dict[str, Any]) -> str:
    """Chave SHA-256 completa dos componentes."""
    return canonical_sha256(components)


class CachedEnrichment(ContractModel):
    """Entrada persistida: chave, análise, componentes e resultado com hash."""

    schema_version: SchemaVersionOne = 1
    cache_key: Sha256Hex
    analysis_id: CanonicalUUID
    key_components: dict[str, Any]
    result: FieldEnrichmentResult
    result_sha256: Sha256Hex

    @model_validator(mode="after")
    def _same_field(self) -> Self:
        """Resultado é exatamente do campo, análise, diagnóstico e contexto da chave."""
        field = self.result.field
        components = self.key_components
        expected = {
            "analysis_id": str(self.analysis_id),
            "analysis_identity_sha256": field.analysis_identity_sha256,
            "diagnostic_sha256": field.diagnostic_sha256,
            "element": field.element.model_dump(mode="json"),
            "requirement": field.requirement.key(),
            "target": [field.target_set_name, field.target_field_name],
            "context_sha256": self.result.context_sha256,
        }
        if str(field.analysis_id) != str(self.analysis_id) or any(
            components.get(name) != value for name, value in expected.items()
        ):
            raise ValueError("resultado não pertence ao campo/análise dos componentes")
        return self


class CatalogCache:
    """Acesso ao cache dentro da transação operacional."""

    def __init__(self, uow: OperationalUnitOfWork) -> None:
        """Usa a unidade de trabalho corrente (mesma transação do resultado/recibo)."""
        self._uow = uow
        self._stored: dict[str, tuple[DiagnosticSnapshot, EnrichmentRun]] = {}

    def _stored_run(
        self, analysis_id: str, context_sha256: str | None
    ) -> tuple[DiagnosticSnapshot, EnrichmentRun] | None:
        """Snapshot e run M3 gravados da análise que contêm o contexto (memoizado)."""
        for stored in self._uow.enrichments.scan(analysis_id=analysis_id):
            key = stored.document["enrichment_id"]
            if key not in self._stored:
                row = self._uow.diagnostics.get(stored.document["snapshot_id"])
                if row is None:
                    raise CacheIntegrityError(f"run M3 {key} sem snapshot gravado")
                try:
                    self._stored[key] = (
                        DiagnosticSnapshot.model_validate(row.document),
                        EnrichmentRun.model_validate(stored.document["run"]),
                    )
                except ValidationError as exc:
                    raise CacheIntegrityError(f"run M3 {key} gravado inválido") from exc
            snapshot, run = self._stored[key]
            if any(c.context_sha256 == context_sha256 for c in run.contexts):
                return snapshot, run
        return None

    def _resolve(self, entry: CachedEnrichment) -> None:
        """Análise, snapshot e run M3 com o contexto citado existem na autoridade."""
        from src.validation.analysis_identity import AnalysisRun

        analysis_id = str(entry.analysis_id)
        components = entry.key_components
        row = self._uow.analyses.get(analysis_id)
        if row is None or (
            AnalysisRun.model_validate(row.document).identity.digest()
            != components.get("analysis_identity_sha256")
        ):
            raise CacheIntegrityError(f"entrada {entry.cache_key}: análise ausente ou divergente")
        found = self._stored_run(analysis_id, entry.result.context_sha256)
        if found is None:
            raise CacheIntegrityError(f"entrada {entry.cache_key}: contexto ausente")
        snapshot, run = found
        if snapshot.content_sha256 != components.get("diagnostic_sha256"):
            raise CacheIntegrityError(f"entrada {entry.cache_key}: diagnóstico ausente")
        stored = next(
            (r for r in run.results if r.field.sort_key() == entry.result.field.sort_key()), None
        )
        if stored != entry.result:
            raise CacheIntegrityError(f"entrada {entry.cache_key}: resultado difere do run gravado")
        context = next(c for c in run.contexts if c.context_sha256 == entry.result.context_sha256)
        bundle = _StoredBundle(run.identity.operation_bundle_sha256, AUTHORIZED_HANDLERS)
        if cache_components(snapshot, context, bundle) != components:
            raise CacheIntegrityError(
                f"entrada {entry.cache_key}: componentes diferem dos recomputados"
            )

    def get(self, key: str) -> CachedEnrichment | None:
        """Entrada revalidada, ou ``None``; adulteração é ``CacheIntegrityError``."""
        row = self._uow.cache.get(key)
        if row is None:
            return None
        try:
            entry = CachedEnrichment.model_validate(row.document)
        except ValidationError as exc:
            raise CacheIntegrityError(f"entrada {key} inválida") from exc
        self._resolve(entry)
        if entry.cache_key != key or cache_key(entry.key_components) != key:
            raise CacheIntegrityError(f"entrada {key} com componentes divergentes")
        if canonical_sha256(entry.result.model_dump(mode="json")) != entry.result_sha256:
            raise CacheIntegrityError(f"entrada {key} com resultado adulterado")
        if entry.key_components.get("analysis_id") != str(entry.analysis_id):
            raise CacheIntegrityError(f"entrada {key} de outra análise")
        return entry

    def put(self, key: str, components: dict[str, Any], result: FieldEnrichmentResult) -> None:
        """INSERT único por chave; mesma chave com outro payload é colisão."""
        if cache_key(components) != key:
            raise ValueError("chave não corresponde aos componentes")
        try:
            entry = CachedEnrichment(
                cache_key=key,
                analysis_id=components["analysis_id"],
                key_components=components,
                result=result,
                result_sha256=canonical_sha256(result.model_dump(mode="json")),
            )
        except ValidationError as exc:
            raise CacheIntegrityError(f"entrada {key} incoerente: {exc}") from exc
        existing = self.get(key)
        if existing is not None:
            if existing.model_dump(mode="json") != entry.model_dump(mode="json"):
                raise CacheCollisionError(f"chave {key} já guarda outro resultado")
            return
        self._resolve(entry)
        self._uow.cache.insert(entry.model_dump(mode="json"))
