"""Identidade de análise, verificador e perfil de execução (M2; plano §2.1).

``VerifierIdentity`` é calculada do runtime e dos arquivos efetivos — código do
verificador, lock de dependências, versões instaladas, bundle IDS, manifesto de
capacidade e opções do backend —, nunca de literais fictícios. ``condition_id``
``m1-e3-evidence-v1`` identifica a condição técnica determinística; seu hash de
configuração cobre limites, manifesto, opções, receita/operações e versões de
contexto. Não altera ``PROMPT_VERSION`` nem promete instrumento experimental.

``AnalysisIdentity`` é **uma** só e fica congelada ao enfileirar, inclusive quando o
resultado será erro. ``AnalysisRun`` tem transições monotônicas; estado terminal é
imutável e retomar um run interrompido cria sucessor.
"""

import hashlib
import importlib.metadata
import platform
from functools import lru_cache
from pathlib import Path
from typing import Final, Literal, Self

from pydantic import Field, model_validator

from src.domain_catalog.actor import ActorSnapshot
from src.domain_catalog.contracts import CatalogReleaseRef, ContractModel
from src.domain_catalog.models import NonEmptyText, Sha256Hex
from src.domain_catalog.package import UtcTimestamp
from src.domain_catalog.provenance import CatalogProvenance
from src.operations.contracts import (
    CanonicalUUID,
    PositiveInt,
    SchemaVersionOne,
    SourceArtifactRef,
    canonical_sha256,
)

CONDITION_ID: Final = "m1-e3-evidence-v1"
VERIFIER_NAME: Final = "ifcqc-ids-verifier"
VERIFIER_VERSION: Final = "1.0.0"
REPO_ROOT: Final = Path(__file__).resolve().parents[2]
MiB: Final = 1024 * 1024

VERIFIER_MODULES: Final[tuple[str, ...]] = (
    "src/ifc_analyzer/element_context.py",
    "src/ifc_analyzer/identity.py",
    "src/ifc_analyzer/observations.py",
    "src/ifc_analyzer/read_only.py",
    "src/translator/ids_document.py",
    "src/validation/aggregation.py",
    "src/validation/analysis_identity.py",
    "src/validation/analysis_service.py",
    "src/validation/candidate_validation.py",
    "src/validation/catalog_analysis.py",
    "src/validation/diagnostic_models.py",
    "src/validation/ids_constraints.py",
    "src/validation/ids_engine.py",
    "src/validation/ifctester_adapter.py",
    "src/validation/schema_bundle.py",
    "src/validation/source_gate.py",
)
"""Arquivos de código cujo conteúdo define o verificador desta condição."""

M3_MODULES: Final[tuple[str, ...]] = (
    "src/domain_catalog/operations.py",
    "src/suggestion_engine/catalog_cache.py",
    "src/suggestion_engine/catalog_context.py",
    "src/suggestion_engine/catalog_contracts.py",
    "src/suggestion_engine/catalog_evidence.py",
    "src/suggestion_engine/catalog_operations.py",
    "src/suggestion_engine/catalog_service.py",
)
"""Código M3 (contexto, avaliação, operações, cache) congelado na condição (E3-05)."""

CONDITION_OPERATIONS: Final = (
    ("normalize_code_nfc_trim", "1.0.0"),
    ("recover_exact_property", "1.0.0"),
)
CONDITION_RECIPE: Final = {"recipe_id": "literal-property-evidence", "version": "1.0.0"}
CONDITION_CONTEXT_VERSIONS: Final = {"local_context": "m1-local-context-v1", "cache": "cache-v1"}


class VerifierIdentity(ContractModel):
    """Verificador IDS exato do runtime; todos os hashes vêm de arquivos efetivos."""

    schema_version: SchemaVersionOne = 1
    name: Literal["ifcqc-ids-verifier"] = VERIFIER_NAME
    version: NonEmptyText
    code_sha256: Sha256Hex
    dependency_lock_sha256: Sha256Hex
    python_version: NonEmptyText
    ifcopenshell_version: NonEmptyText
    ifctester_version: NonEmptyText
    xmlschema_version: NonEmptyText
    lxml_version: NonEmptyText
    schema_bundle_sha256: Sha256Hex
    capability_manifest_sha256: Sha256Hex
    options_sha256: Sha256Hex


StrictPositive = Field(ge=1)


class ExecutionLimits(ContractModel):
    """Guardas determinísticas da condição (plano §6); igualdade é permitida."""

    max_ifc_bytes: int = Field(default=256 * MiB, ge=1, strict=True)
    max_ids_bytes: int = Field(default=8 * MiB, ge=1, strict=True)
    max_xml_depth: int = Field(default=64, ge=1, strict=True)
    max_xml_nodes: int = Field(default=100_000, ge=1, strict=True)
    max_ifc_entities: int = Field(default=250_000, ge=1, strict=True)
    max_result_rows: int = Field(default=250_000, ge=1, strict=True)
    max_selectors_per_field: int = Field(default=64, ge=1, strict=True)
    max_observations_per_field: int = Field(default=512, ge=1, strict=True)
    max_context_bytes: int = Field(default=1 * MiB, ge=1, strict=True)


class ExecutionProfile(ContractModel):
    """Verificador, condição e configuração exatos que este runtime cumpre."""

    verifier: VerifierIdentity
    condition_id: Literal["m1-e3-evidence-v1"] = CONDITION_ID
    condition_config_sha256: Sha256Hex
    limits: ExecutionLimits


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha_source(path: Path) -> str:
    """SHA-256 do código com fins de linha normalizados para LF (``.gitattributes``)."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def code_sha256(root: Path = REPO_ROOT) -> str:
    """Hash do conjunto de módulos do verificador (caminho → SHA-256 do código em LF)."""
    return canonical_sha256({name: _sha_source(root / name) for name in VERIFIER_MODULES})


def m3_code_sha256(root: Path = REPO_ROOT) -> str:
    """Hash do código M3 da condição (caminho → SHA-256 do código em LF)."""
    return canonical_sha256({name: _sha_source(root / name) for name in M3_MODULES})


@lru_cache(maxsize=1)
def _m3_code() -> str:
    return m3_code_sha256(REPO_ROOT)


@lru_cache(maxsize=1)
def operation_manifest_sha256() -> str:
    """Manifesto do bundle M3 desta condição (specs, precondições e implementações)."""
    from src.suggestion_engine.catalog_operations import build_e3_operation_bundle

    return build_e3_operation_bundle().manifest_sha256


def condition_config_sha256(
    limits: ExecutionLimits,
    capability_manifest_sha256: str,
    options_sha256: str,
    *,
    m3_code: str | None = None,
    operation_manifest: str | None = None,
) -> str:
    """Hash da condição: limites, capacidade, opções, receita, operações, código M3 e
    manifesto do bundle (omitidos = os do runtime atual)."""
    return canonical_sha256(
        {
            "condition_id": CONDITION_ID,
            "limits": limits.model_dump(mode="json"),
            "capability_manifest_sha256": capability_manifest_sha256,
            "options_sha256": options_sha256,
            "recipe": CONDITION_RECIPE,
            "operations": [list(item) for item in CONDITION_OPERATIONS],
            "context_versions": CONDITION_CONTEXT_VERSIONS,
            "m3_code_sha256": m3_code or _m3_code(),
            "operation_manifest_sha256": operation_manifest or operation_manifest_sha256(),
        }
    )


@lru_cache(maxsize=4)
def _verifier(root: Path) -> VerifierIdentity:
    from src.validation.ids_constraints import CAPABILITY_MANIFEST_SHA256
    from src.validation.ifctester_adapter import BACKEND_OPTIONS_SHA256
    from src.validation.schema_bundle import SchemaBundle

    lock = root / "uv.lock"
    return VerifierIdentity(
        version=VERIFIER_VERSION,
        code_sha256=code_sha256(root),
        dependency_lock_sha256=_sha_file(lock),
        python_version=platform.python_version(),
        ifcopenshell_version=importlib.metadata.version("ifcopenshell"),
        ifctester_version=importlib.metadata.version("ifctester"),
        xmlschema_version=importlib.metadata.version("xmlschema"),
        lxml_version=importlib.metadata.version("lxml"),
        schema_bundle_sha256=SchemaBundle.load().manifest_sha256,
        capability_manifest_sha256=CAPABILITY_MANIFEST_SHA256,
        options_sha256=BACKEND_OPTIONS_SHA256,
    )


def current_execution_profile(limits: ExecutionLimits | None = None) -> ExecutionProfile:
    """Perfil do runtime atual, calculado dos arquivos e pacotes efetivos."""
    limits = limits or ExecutionLimits()
    verifier = _verifier(REPO_ROOT)
    return ExecutionProfile(
        verifier=verifier,
        condition_config_sha256=condition_config_sha256(
            limits, verifier.capability_manifest_sha256, verifier.options_sha256
        ),
        limits=limits,
    )


CatalogState = Literal["available", "not_attached", "invalid", "unavailable"]


class AnalysisIdentity(ContractModel):
    """Identidade única e congelada de uma análise de um par IFC–IDS."""

    schema_version: SchemaVersionOne = 1
    project_id: CanonicalUUID
    analysis_id: CanonicalUUID
    pair_id: CanonicalUUID
    pair_revision: PositiveInt
    ifc: SourceArtifactRef
    ids: SourceArtifactRef
    catalog_ref: CatalogReleaseRef | None = None
    pin_revision: PositiveInt | None = None
    catalog_provenance: CatalogProvenance | None = None
    catalog_state: CatalogState
    verifier: VerifierIdentity
    condition_id: Literal["m1-e3-evidence-v1"] = CONDITION_ID
    condition_config_sha256: Sha256Hex
    limits: ExecutionLimits

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        """Fontes do mesmo projeto/modelo e estado do catálogo coerente com ref/pin."""
        if (self.ifc.role, self.ids.role) != ("ifc", "ids"):
            raise ValueError("identidade exige fonte ifc e fonte ids")
        if {self.ifc.project_id, self.ids.project_id} != {self.project_id}:
            raise ValueError("fontes de outro projeto")
        if self.ifc.model_id != self.ids.model_id:
            raise ValueError("fontes de modelos diferentes")
        triple = (self.catalog_ref, self.pin_revision, self.catalog_provenance)
        present = [item is not None for item in triple]
        if self.catalog_state == "available" and not all(present):
            raise ValueError("catálogo available exige ref, pin e proveniência")
        if self.catalog_state == "not_attached" and any(present):
            raise ValueError("catálogo not_attached não admite ref/pin/proveniência")
        if self.catalog_state in ("invalid", "unavailable") and any(present) and not all(present):
            raise ValueError("ref/pin/proveniência esperados ficam completos ou ausentes")
        provenance = self.catalog_provenance
        if provenance is not None and provenance.catalog != self.catalog_ref:
            raise ValueError("proveniência pertence a outro release")
        return self

    def digest(self) -> str:
        """Hash canônico da identidade (comparado no comando de execução)."""
        return canonical_sha256(self.model_dump(mode="json"))


AnalysisState = Literal["queued", "running", "completed", "failed", "interrupted"]
TERMINAL_STATES: Final = frozenset({"completed", "failed", "interrupted"})
_ALLOWED: Final[dict[str, frozenset[str]]] = {
    "queued": frozenset({"running"}),
    "running": frozenset({"completed", "failed", "interrupted"}),
}


class ExecutionClaim(ContractModel):
    """Posse de execução: tokens do executor/coordenador e comando de execução."""

    execution_token: CanonicalUUID
    coordinator_token: CanonicalUUID
    command_id: CanonicalUUID
    claimed_at_utc: UtcTimestamp


class RunProblem(ContractModel):
    """Problema técnico registrado no run (código estável e mensagem)."""

    code: NonEmptyText
    message: NonEmptyText


class RunCompletion(ContractModel):
    """Referências gravadas no fim (snapshot, enriquecimento, comando e recibo)."""

    snapshot_id: CanonicalUUID | None = None
    diagnostic_sha256: Sha256Hex | None = None
    enrichment_id: CanonicalUUID | None = None
    enrichment_sha256: Sha256Hex | None = None
    command_id: CanonicalUUID
    receipt_id: CanonicalUUID


class AnalysisRun(ContractModel):
    """Run de análise com identidade congelada e estado monotônico."""

    schema_version: SchemaVersionOne = 1
    analysis_id: CanonicalUUID
    identity: AnalysisIdentity
    state: AnalysisState
    state_version: PositiveInt
    parent_analysis_id: CanonicalUUID | None = None
    queued_by: ActorSnapshot
    queue_reason: NonEmptyText
    queued_at_utc: UtcTimestamp
    claim: ExecutionClaim | None = None
    started_at_utc: UtcTimestamp | None = None
    finished_at_utc: UtcTimestamp | None = None
    completion: RunCompletion | None = None
    problems: tuple[RunProblem, ...] = ()

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        """Identidade, posse, tempos e conclusão coerentes com o estado."""
        if self.identity.analysis_id != self.analysis_id:
            raise ValueError("identidade de outro run")
        if self.parent_analysis_id == self.analysis_id:
            raise ValueError("run não é pai de si mesmo")
        if self.state == "queued" and (self.claim or self.started_at_utc or self.finished_at_utc):
            raise ValueError("run enfileirado não tem posse nem tempos de execução")
        if self.state == "running" and (self.claim is None or self.started_at_utc is None):
            raise ValueError("run em execução exige posse e início")
        if self.state in TERMINAL_STATES and self.finished_at_utc is None:
            raise ValueError("run terminal exige fim")
        if self.state == "completed" and self.completion is None:
            raise ValueError("run concluído exige referências de conclusão")
        if self.state in ("failed", "interrupted") and not self.problems:
            raise ValueError("run falho ou interrompido exige problema registrado")
        return self

    def advance(self, state: AnalysisState, **changes: object) -> "AnalysisRun":
        """Próximo estado permitido; terminal é imutável."""
        if state not in _ALLOWED.get(self.state, frozenset()):
            raise ValueError(f"transição {self.state} → {state} não permitida")
        return AnalysisRun.model_validate(
            {
                **self.model_dump(),
                **changes,
                "state": state,
                "state_version": self.state_version + 1,
            }
        )
