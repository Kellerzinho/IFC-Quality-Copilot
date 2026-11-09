"""Contratos da adoção de catálogo por projeto (E3.2b, M1-11; plano §4).

``CatalogAdoptionPlan`` é imutável e persistido: alvo retido com proveniência
verificada, tokens esperados, lista completa e ordenada dos pares congelados, perfil
de execução, diff E3.2a (ou ausência explícita ``no_previous_catalog`` na adoção
inicial) e escopo conservador de reanálise. A confirmação é um comando humano que
cita só o ID e o hash do plano. Nenhuma análise resolve ``latest``, rascunho ou pin
corrente depois de congelar sua identidade.
"""

import uuid
from typing import Literal, Self

from pydantic import Field, model_validator

from src.artifacts.contracts import RetainedCatalogRef
from src.domain_catalog.actor import ActorSnapshot
from src.domain_catalog.contracts import CatalogReleaseRef, ContractModel
from src.domain_catalog.diff_contracts import CatalogDiff
from src.domain_catalog.models import NonEmptyText, Sha256Hex
from src.domain_catalog.package import ContentOrigin, UtcTimestamp
from src.domain_catalog.provenance import CatalogProvenance
from src.operations.analysis_queue import AnalysisQueueReceipt
from src.operations.contracts import (
    CanonicalUUID,
    NonNegativeInt,
    OperationalReceipt,
    SchemaVersionOne,
    canonical_sha256,
)
from src.operations.project_models import ModelPairBinding, ProjectCatalogPin
from src.validation.analysis_identity import ExecutionProfile

AdoptionIntent = Literal["initial", "update", "rollback"]

MigrationErrorReason = Literal[
    "not_found",
    "invalid_actor",
    "human_actor_required",
    "invalid_command",
    "intent_mismatch",
    "no_active_pairs",
    "stale_pin",
    "stale_pair_set",
    "stale_plan",
    "plan_hash_mismatch",
    "idempotency_conflict",
    "execution_profile_mismatch",
    "artifact_unavailable",
    "artifact_integrity_error",
    "unpublished_release",
    "synthetic_catalog_forbidden",
    "version_hash_collision",
    "store_busy",
]


class MigrationError(Exception):
    """Adoção recusada sem efeito, com projeto, plano e tokens comparados."""

    code = "migration_refused"

    def __init__(
        self,
        reason: MigrationErrorReason,
        message: str,
        *,
        project_id: uuid.UUID | None = None,
        plan_id: uuid.UUID | None = None,
        expected: object | None = None,
        actual: object | None = None,
    ) -> None:
        """Guarda o motivo estável; a causa original fica em ``__cause__``."""
        self.reason: MigrationErrorReason = reason
        self.project_id = project_id
        self.plan_id = plan_id
        self.expected = expected
        self.actual = actual
        super().__init__(f"[{reason}] {message}")


class RetainedReleaseRecord(ContractModel):
    """Registro de release retido na autoridade; retenção não é publicação."""

    schema_version: SchemaVersionOne = 1
    catalog: CatalogReleaseRef
    storage_key: NonEmptyText
    retained: RetainedCatalogRef
    origin: Literal["retained_local_package"] = "retained_local_package"
    content_origin: ContentOrigin

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        """Ref e chave iguais às do objeto retido."""
        if (self.retained.catalog, self.retained.storage_key) != (self.catalog, self.storage_key):
            raise ValueError("registro difere do objeto retido")
        return self


class FrozenPair(ContractModel):
    """Par congelado no plano e a análise anterior que será pai da nova."""

    pair: ModelPairBinding
    parent_analysis_id: CanonicalUUID | None = None


class CatalogAdoptionPlan(ContractModel):
    """Plano imutável de adoção, atualização ou rollback de catálogo num projeto."""

    schema_version: SchemaVersionOne = 1
    plan_id: CanonicalUUID
    project_id: CanonicalUUID
    intent: AdoptionIntent
    reason: NonEmptyText
    old_pin_revision: NonNegativeInt
    old_ref: CatalogReleaseRef | None
    target_ref: CatalogReleaseRef
    target_retained: RetainedCatalogRef
    target_provenance: CatalogProvenance
    expected_pin_revision: NonNegativeInt
    expected_pair_set_revision: NonNegativeInt
    pairs: tuple[FrozenPair, ...] = Field(min_length=1)
    execution_profile: ExecutionProfile
    diff: CatalogDiff | None
    diff_sha256: Sha256Hex | None
    diff_absent_reason: Literal["no_previous_catalog"] | None
    reanalysis_scope: Literal["all_active_pairs"] = "all_active_pairs"
    requirement_impact: Literal["conservative_all"] = "conservative_all"
    informative_requirement_refs: tuple[str, ...] = ()
    prepared_by: ActorSnapshot
    prepared_at_utc: UtcTimestamp

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        """Intenção, diff, tokens, alvo e pares coerentes entre si."""
        if self.target_retained.catalog != self.target_ref:
            raise ValueError("alvo retido difere da referência")
        if (
            self.target_provenance.catalog != self.target_ref
            or not self.target_provenance.published
        ):
            raise ValueError("plano exige proveniência publicada do próprio alvo")
        if self.expected_pin_revision != self.old_pin_revision:
            raise ValueError("token esperado difere do pin congelado")
        if self.intent == "initial":
            if (self.old_ref, self.diff, self.diff_sha256) != (None, None, None):
                raise ValueError("adoção inicial não tem release anterior nem diff")
            if self.diff_absent_reason != "no_previous_catalog" or self.old_pin_revision != 0:
                raise ValueError("adoção inicial declara no_previous_catalog com token 0")
        else:
            if self.old_ref is None or self.diff is None or self.old_pin_revision == 0:
                raise ValueError("atualização/rollback exigem pin anterior e diff")
            if self.diff_absent_reason is not None:
                raise ValueError("diff presente não tem motivo de ausência")
            if (self.diff.old_ref, self.diff.new_ref) != (self.old_ref, self.target_ref):
                raise ValueError("diff não é entre o pin corrente e o alvo")
            if self.diff_sha256 != canonical_sha256(self.diff.model_dump(mode="json")):
                raise ValueError("diff_sha256 não corresponde ao diff")
        ids = [str(item.pair.pair_id) for item in self.pairs]
        if ids != sorted(set(ids)):
            raise ValueError("pares congelados únicos e ordenados por pair_id")
        if any(
            item.pair.project_id != self.project_id or not item.pair.active for item in self.pairs
        ):
            raise ValueError("pares congelados precisam ser ativos e do projeto")
        return self


def plan_digest(plan: CatalogAdoptionPlan) -> str:
    """Hash canônico do plano persistido (confirmado pelo comando de aplicação)."""
    return canonical_sha256(plan.model_dump(mode="json"))


class AdoptionReceipt(ContractModel):
    """Recibo da aplicação: comando, plano/hash, novo pin e análises enfileiradas."""

    schema_version: SchemaVersionOne = 1
    operational: OperationalReceipt
    project_id: CanonicalUUID
    plan_id: CanonicalUUID
    plan_sha256: Sha256Hex
    intent: AdoptionIntent
    status: Literal["applied", "noop"]
    adoption_id: CanonicalUUID | None = None
    pin: ProjectCatalogPin | None = None
    queued_analysis_ids: tuple[CanonicalUUID, ...] = ()

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        """Aplicação cria pin e análises; noop não cria nada."""
        if self.status == "applied":
            if self.adoption_id is None or self.pin is None or not self.queued_analysis_ids:
                raise ValueError("adoção aplicada exige adoção, pin e análises enfileiradas")
            if self.pin.adoption_id != self.adoption_id:
                raise ValueError("pin de outra adoção")
        elif self.adoption_id is not None or self.pin is not None or self.queued_analysis_ids:
            raise ValueError("noop não cria pin nem análise")
        if self.operational.status != self.status:
            raise ValueError("status difere do recibo operacional")
        return self


ReanalysisReceipt = AnalysisQueueReceipt
"""Recibo de reanálise: mesmo contrato de enfileiramento, sem revisão de pin."""
