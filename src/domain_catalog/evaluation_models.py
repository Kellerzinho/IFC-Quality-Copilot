"""Contratos da avaliação da condição de catálogo ``m1-e4-catalog-eval-v1`` (M1-15).

Formato ``ifcqc-catalog-evaluation-1``. Separa cobertura documental, cadastro,
capacidade por caso, abstenção, falso mapeamento e erro de pacote. Qualidade só é
calculada sobre referência elegível: fixture sintética fica em bloco próprio e
referência humana declarada vira "concordância com referência declarada", nunca
qualidade de domínio aceita (não há autenticação de pessoa). Nada aqui altera
``ExecutionProfile.condition_id`` (``m1-e3-evidence-v1``) nem o instrumento legado.
"""

from typing import Annotated, Literal

from pydantic import Field, StrictInt, StringConstraints, model_validator

from src.domain_catalog.contracts import BindingRequest, CatalogReleaseRef, ResolutionStatus
from src.domain_catalog.models import (
    CatalogModel,
    FormatVersionOne,
    LocalId,
    NonEmptyText,
    Sha256Hex,
)

EVALUATION_FORMAT = "ifcqc-catalog-evaluation-1"
EVALUATION_CONDITION_ID = "m1-e4-catalog-eval-v1"
EVALUATOR_VERSION = "1.0.0"
CaseId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")]
CountInt = Annotated[StrictInt, Field(ge=0)]
CaseOrigin = Literal["synthetic", "daiane_source", "expert_reference"]
Split = Literal["development", "evaluation"]
QualityBlockKind = Literal["not_measured", "synthetic_reference", "declared_reference_agreement"]


class CaseExpectation(CatalogModel):
    """Gabarito do caso: estados admitidos e, se resolvível, o uso correto."""

    allowed_statuses: tuple[ResolutionStatus, ...] = Field(min_length=1)
    binding_id: LocalId | None = None
    concept_id: LocalId | None = None
    candidate_binding_ids: tuple[LocalId, ...] = ()

    @model_validator(mode="after")
    def _pair(self) -> "CaseExpectation":
        """Binding e conceito esperados aparecem juntos."""
        if (self.binding_id is None) != (self.concept_id is None):
            raise ValueError("binding_id e concept_id esperados aparecem juntos")
        return self

    @property
    def resolvable(self) -> bool:
        """Referência exige um uso resolvido."""
        return self.binding_id is not None


class CatalogEvaluationCase(CatalogModel):
    """Caso de avaliação com proveniência; o resultado do resolver nunca é o gabarito."""

    case_id: CaseId
    request: BindingRequest
    origin: CaseOrigin
    stratum: NonEmptyText
    family: NonEmptyText | None = None
    facet: NonEmptyText
    split: Split
    source_refs: tuple[NonEmptyText, ...] = ()
    source_sha256: Sha256Hex | None = None
    exclusion_reason: NonEmptyText | None = None
    expectation: CaseExpectation | None = None


class CatalogEvaluationCorpus(CatalogModel):
    """Corpus de consultas com autoria e método de geração declarados."""

    format: Literal["ifcqc-catalog-evaluation-1"]
    format_version: FormatVersionOne
    corpus_id: NonEmptyText
    generated_by: NonEmptyText
    generation_method: NonEmptyText
    cases: tuple[CatalogEvaluationCase, ...]


class UniqueQuery(CatalogModel):
    """Consulta única (JSON canônico do pedido sem ``requirement_ref``) e sua proveniência."""

    query_key: NonEmptyText
    request: BindingRequest
    case_ids: tuple[CaseId, ...]
    source_refs: tuple[NonEmptyText, ...]
    split: Split
    origins: tuple[CaseOrigin, ...]
    excluded: bool
    reference_conflict: bool = False


class DeduplicatedCorpus(CatalogModel):
    """Corpus deduplicado: denominadores totais, incluídos e excluídos com motivo."""

    total_cases: CountInt
    total_unique: CountInt
    included: CountInt
    excluded: CountInt
    excluded_cases: tuple[tuple[str, str], ...] = ()
    queries: tuple[UniqueQuery, ...]
    conflicts: tuple[str, ...] = ()
    strata: dict[str, int] = Field(default_factory=dict)
    """Consultas únicas incluídas por estrato, só das consultas de um único estrato."""
    multi_stratum_queries: tuple[str, ...] = ()
    strata_only_in_shared_queries: tuple[str, ...] = ()
    """Estratos sem consulta própria: só aparecem em consultas idênticas a outro estrato."""


class CatalogCaseResult(CatalogModel):
    """Resultado de uma consulta única executada pelo reader real (ou fixture do agregador)."""

    query_key: NonEmptyText
    case_ids: tuple[CaseId, ...]
    status: ResolutionStatus
    binding_id: LocalId | None = None
    concept_id: LocalId | None = None
    reasons: tuple[str, ...] = ()


class RateValue(CatalogModel):
    """Taxa reconstruível: numerador, denominador e motivo quando nula."""

    value: float | None
    numerator: CountInt
    denominator: CountInt
    reason: str | None = None


class QualityBlock(CatalogModel):
    """Qualidade só sobre referência elegível; rótulo explícito do tipo de referência."""

    block: QualityBlockKind
    eligible_cases: CountInt
    blocked_by_conflict: CountInt = 0
    resolved_with_reference: CountInt = 0
    correct_resolved: CountInt = 0
    false_mapping: CountInt = 0
    reference_resolvable: CountInt = 0
    status_matches: CountInt = 0
    mapping_precision: RateValue
    mapping_recall: RateValue
    status_accuracy: RateValue


class CatalogScoreSummary(CatalogModel):
    """Contagens dos estados reais e taxas sobre o denominador declarado."""

    result_count: CountInt
    denominator_label: NonEmptyText
    metrics_label: Literal["synthetic_contract", "real_corpus"]
    by_status: dict[str, int]
    resolved: CountInt
    abstentions: CountInt
    errors: CountInt
    rates: dict[str, RateValue]
    quality: QualityBlock
    domain_quality: Literal["not_measured", "declared_reference_agreement"]


class InputArtifact(CatalogModel):
    """Artefato usado na condição, com bytes fornecidos explicitamente e hash declarado."""

    role: Literal["profile", "source", "transcription", "ledger", "protocol", "reference", "code"]
    label: NonEmptyText
    sha256: Sha256Hex
    data: bytes


class CatalogEvaluationInputs(CatalogModel):
    """Artefatos e runtime efetivamente usados; nada é escolhido implicitamente."""

    artifacts: tuple[InputArtifact, ...] = ()
    runtime: dict[str, str] = Field(default_factory=dict)


class CatalogEvaluationCondition(CatalogModel):
    """Condição derivada do que foi aberto e usado; sem horário, latência ou caminho."""

    condition_id: Literal["m1-e4-catalog-eval-v1"]
    evaluator_version: NonEmptyText
    catalog_ref: CatalogReleaseRef
    content_sha256: Sha256Hex
    manifest_sha256: Sha256Hex
    corpus_sha256: Sha256Hex
    input_artifacts: dict[str, str]
    case_records_sha256: Sha256Hex
    reference_review_sha256: Sha256Hex | None
    reference_eligible_case_ids: tuple[str, ...]
    code_sha256: dict[str, str]
    operation_ids: tuple[str, ...]
    runtime: dict[str, str]
    """Runtime declarado por quem executa (proveniência; não conferido)."""
    measured_runtime: dict[str, str]
    """Python, implementação e Pydantic medidos no próprio processo da avaliação."""
    condition_sha256: Sha256Hex


class ReferenceReview(CatalogModel):
    """Registro de revisão de referência, separado do corpus e conferido por hash.

    ``reviewer_declared`` é declaração local: o software mede concordância com a
    referência declarada, sem certificar pessoa nem aceite científico.
    """

    format: Literal["ifcqc-catalog-reference-review-1"]
    format_version: FormatVersionOne
    corpus_sha256: Sha256Hex
    labels_sha256: Sha256Hex
    case_ids: tuple[CaseId, ...] = Field(min_length=1)
    reviewer_declared: NonEmptyText
    generator_declared: NonEmptyText
    date: Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}$")]
    method: NonEmptyText
    evidence_file: NonEmptyText
    evidence_sha256: Sha256Hex
    status: Literal["accepted", "pending", "rejected"]


class ReferenceEligibility(CatalogModel):
    """Casos elegíveis para concordância com referência declarada e motivos de recusa."""

    eligible_case_ids: tuple[CaseId, ...]
    block: QualityBlockKind
    corpus_sha256: Sha256Hex
    labels_sha256: Sha256Hex
    review_sha256: Sha256Hex
    identity_assurance: Literal["unverified_local"] = "unverified_local"
    reasons: tuple[str, ...] = ()


class CatalogEvaluationReport(CatalogModel):
    """Relatório de uma execução: concluída sobre release aberto ou falha de abertura."""

    run_status: Literal["completed", "package_error"]
    requested_ref: CatalogReleaseRef
    attempt_sha256: Sha256Hex
    condition: CatalogEvaluationCondition | None
    corpus: DeduplicatedCorpus
    executed_cases: CountInt
    not_executed_cases: CountInt
    package_open_errors: CountInt
    package_error_reason: str | None = None
    results: tuple[CatalogCaseResult, ...]
    summary: CatalogScoreSummary


class QuerySample(CatalogModel):
    """Amostras de uma consulta única em reader já aberto, após aquecimento identificado."""

    query_key: NonEmptyText
    warmup_ns: Annotated[StrictInt, Field(ge=1)]
    samples_ns: tuple[int, ...]
    median_ns: float
    p95_ns: int


class CatalogPerformanceReport(CatalogModel):
    """Medição de recurso local; sem SLA, sem RSS e sem cache de SO frio."""

    condition_sha256: Sha256Hex
    corpus_sha256: Sha256Hex
    os_cache_control: Literal["not_controlled"]
    open_samples_ns: tuple[int, ...]
    open_median_ns: float
    open_p95_ns: int
    query_samples: tuple[QuerySample, ...]
    peak_python_heap_bytes: CountInt
    percentile_method: Literal["nearest_rank"]
    environment: dict[str, str]


class CurationEffort(CatalogModel):
    """Ações e conferências registradas; duração humana só com observação real."""

    recorded_actions: dict[str, int]
    human_duration: Literal["not_measured"]
    instrument: NonEmptyText


class ProfileEvaluationSummary(CatalogModel):
    """Cobertura documental do perfil em rascunho: sem reader, ref ou manifesto fictícios."""

    evaluation_mode: Literal["documentary_coverage_only"]
    catalog_ref: None = None
    draft_content_sha256: Sha256Hex
    reconciliation_sha256: Sha256Hex
    by_family_destination: dict[str, dict[str, int]]
    by_category_destination: dict[str, dict[str, int]]
    by_axis: dict[str, dict[str, int]]
    inventory_accounted_for: bool
    domain_review_complete: bool
    profile_operational: bool
    curation_effort: CurationEffort
