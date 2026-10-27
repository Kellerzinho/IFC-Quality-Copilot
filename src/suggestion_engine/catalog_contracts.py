"""Contratos ricos do enriquecimento determinístico M3 por catálogo (plano §7).

Não são convertidos para ``BSDDContext``, ``Issue.context``, ``SuggestionSet`` nem
strings. Um campo é um par elemento/requisito; contexto, avaliação e resultado são
DTOs imutáveis com hash canônico. ``FieldAlternative`` nunca autoriza escrita:
``requires_human_review`` é sempre verdadeiro e o destino é a ocorrência alvo.
"""

from typing import Any, Final, Literal, Self

from pydantic import Field, model_validator

from src.domain_catalog.contracts import (
    BindingRequest,
    CatalogReleaseRef,
    ContractModel,
    ResolutionResult,
)
from src.domain_catalog.models import ChannelCode, LocalId, NonEmptyText, Sha256Hex
from src.domain_catalog.projection_contracts import CatalogProjection
from src.ifc_analyzer.identity import ElementRef
from src.ifc_analyzer.observations import SearchPlan, SearchReport, SelectorCoverage, TypedValue
from src.operations.contracts import CanonicalUUID, SchemaVersionOne, canonical_sha256
from src.validation.analysis_identity import CONDITION_ID, ExecutionLimits, VerifierIdentity
from src.validation.candidate_validation import CandidateValidation
from src.validation.diagnostic_models import ExpectedField, FormalState, RequirementRef

M3Reason = Literal[
    "unmapped",
    "ambiguous_mapping",
    "insufficient_context",
    "unapproved_content",
    "pending_carrier",
    "policy_missing",
    "observed_mapping_mismatch",
    "operation_unavailable",
    "operation_version_mismatch",
    "operation_unpinned",
    "unsupported_precondition",
    "unsupported_schema",
    "unsupported_carrier",
    "unsupported_value_type",
    "unsupported_target_scope",
    "unsupported_candidate_validation",
    "unsupported_channel",
    "no_evidence",
    "null_value",
    "empty_value",
    "invalid_value",
    "incomplete_search",
    "evidence_conflict",
    "duplicate_source_ambiguity",
    "unit_unknown",
    "unit_mismatch",
    "no_matching_code",
    "ambiguous_normalization",
    "context_limit_exceeded",
    "not_applicable",
    "already_satisfied",
    "candidate_violates_requirement",
    "candidate_type_mismatch",
    "formal_not_verified",
    "formal_error",
    "package_error",
    "identity_mismatch",
    "foreign_reference",
    "search_error",
    "storage_unavailable",
    "integrity_error",
    "internal_error",
]
"""Motivos fechados (lista mínima do plano §7.4 mais canal e estados formais)."""

TECHNICAL_REASONS: Final = frozenset(
    {
        "package_error",
        "identity_mismatch",
        "foreign_reference",
        "search_error",
        "storage_unavailable",
        "integrity_error",
        "internal_error",
        "formal_error",
    }
)
UNSUPPORTED_REASONS: Final = frozenset(
    {
        "policy_missing",
        "operation_unavailable",
        "operation_version_mismatch",
        "operation_unpinned",
        "unsupported_precondition",
        "unsupported_schema",
        "unsupported_carrier",
        "pending_carrier",
        "unsupported_value_type",
        "unsupported_target_scope",
        "unsupported_candidate_validation",
        "unsupported_channel",
        "unit_unknown",
        "unit_mismatch",
        "context_limit_exceeded",
        "formal_not_verified",
    }
)
NOT_REQUESTED_REASONS: Final = frozenset({"not_applicable", "already_satisfied"})

AssessmentStatus = Literal["sufficient", "partial", "insufficient", "conflicting", "unavailable"]
ResultStatus = Literal["proposed", "abstained", "unsupported", "failed", "not_requested"]
RequiredAction = Literal["none", "request_human", "request_review"]
MiB: Final = 1024 * 1024


class RecipeLimits(ContractModel):
    """Limites da receita por campo (iguais aos da condição)."""

    max_selectors: int = Field(default=64, ge=1, strict=True)
    max_observations: int = Field(default=512, ge=1, strict=True)
    max_context_bytes: int = Field(default=MiB, ge=1, strict=True)


class ContextRecipe(ContractModel):
    """Manifesto de código fixo da coleta; não é interpretador geral de receitas."""

    recipe_id: Literal["literal-property-evidence"] = "literal-property-evidence"
    version: Literal["1.0.0"] = "1.0.0"
    supported_channels: tuple[ChannelCode, ...] = ("P", "T")
    selector_rule: Literal["literal-approved-binding-aliases-v1"] = (
        "literal-approved-binding-aliases-v1"
    )
    target_scope: Literal["occurrence"] = "occurrence"
    limits: RecipeLimits = Field(default_factory=RecipeLimits)

    def digest(self) -> str:
        """Hash de todos os campos da receita."""
        return canonical_sha256(self.model_dump(mode="json"))


RECIPE: Final = ContextRecipe()
"""Receita desta condição com os limites default."""


def recipe_for(limits: ExecutionLimits) -> ContextRecipe:
    """Receita executada: limites por campo vêm dos ``ExecutionLimits`` congelados (E3-07)."""
    return ContextRecipe(
        limits=RecipeLimits(
            max_selectors=limits.max_selectors_per_field,
            max_observations=limits.max_observations_per_field,
            max_context_bytes=limits.max_context_bytes,
        )
    )


BUILDER: Final = "catalog_context"
BUILDER_VERSION: Final = "1.0.0"
ASSESSMENT_VERSION: Final = "1.0.0"


class FieldRef(ContractModel):
    """Campo: análise/snapshot exatos, elemento, requisito e alvo literal."""

    analysis_id: CanonicalUUID
    analysis_identity_sha256: Sha256Hex
    snapshot_id: CanonicalUUID
    diagnostic_sha256: Sha256Hex
    element: ElementRef
    requirement: RequirementRef
    target_set_name: str | None
    target_field_name: str | None
    binding_id: LocalId | None = None
    concept_id: LocalId | None = None

    def sort_key(self) -> tuple[int, int, int]:
        """Ordem: especificação, requisito, elemento."""
        return (
            self.requirement.specification_index,
            self.requirement.index,
            self.element.express_id,
        )


class ObservedResolution(ContractModel):
    """Resolução do caminho **observado** e sua pertinência ao binding alvo."""

    observation_id: Sha256Hex
    request: BindingRequest
    resolution: ResolutionResult
    admissible: bool
    rejection_reason: M3Reason | None = None
    alias_ids: tuple[LocalId, ...] = ()
    decision_ids: tuple[LocalId, ...] = ()

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        """Rejeição exige motivo; admissão não."""
        if self.admissible == (self.rejection_reason is not None):
            raise ValueError("observação admitida não tem motivo; rejeitada exige motivo")
        return self


_CONTEXT_HASH_EXCLUDE: Final = frozenset({"context_sha256"})


def context_digest(document: dict[str, Any]) -> str:
    """Hash canônico do contexto sem o próprio hash."""
    return canonical_sha256({k: v for k, v in document.items() if k not in _CONTEXT_HASH_EXCLUDE})


class FieldEvidenceContext(ContractModel):
    """Contexto de evidência de um campo, origem ``local_snapshot`` e hash de conteúdo."""

    schema_version: SchemaVersionOne = 1
    field: FieldRef
    formal_state: FormalState
    formal_reason: str | None
    expected: ExpectedField
    verifier: VerifierIdentity
    catalog: CatalogReleaseRef | None
    projection: CatalogProjection | None = None
    unavailable_reason: M3Reason | None = None
    unavailable_detail: str | None = None
    search_plan: SearchPlan | None = None
    search_report: SearchReport | None = None
    resolutions: tuple[ObservedResolution, ...] = ()
    recipe: ContextRecipe
    builder: Literal["catalog_context"] = BUILDER
    builder_version: Literal["1.0.0"] = BUILDER_VERSION
    condition_id: Literal["m1-e3-evidence-v1"] = CONDITION_ID
    origin: Literal["local_snapshot"] = "local_snapshot"
    context_sha256: Sha256Hex

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        """Hash, alvo literal, plano/relatório e resoluções coerentes."""
        if self.context_sha256 != context_digest(self.model_dump(mode="json")):
            raise ValueError("context_sha256 não corresponde ao contexto")
        if self.expected.requirement != self.field.requirement:
            raise ValueError("esperado de outro requisito")
        expected_target = (
            None if self.expected.set_name is None else self.expected.set_name.text,
            None if self.expected.field_name is None else self.expected.field_name.text,
        )
        if (self.field.target_set_name, self.field.target_field_name) != expected_target:
            raise ValueError("alvo literal difere do esperado IDS")
        if (self.search_report is None) != (self.search_plan is None):
            raise ValueError("plano e relatório de busca existem juntos")
        if self.search_report is not None and self.search_report.plan != self.search_plan:
            raise ValueError("relatório de outro plano")
        observed = (
            set()
            if self.search_report is None
            else {o.observation_id for o in self.search_report.observations}
        )
        if any(r.observation_id not in observed for r in self.resolutions):
            raise ValueError("resolução de observação fora do relatório")
        if self.projection is not None and self.projection.binding.id != self.field.binding_id:
            raise ValueError("projeção de outro binding")
        return self

    def observation(self, observation_id: str) -> Any:
        """Observação do relatório pelo ID."""
        assert self.search_report is not None
        return next(
            o for o in self.search_report.observations if o.observation_id == observation_id
        )


class RejectedObservation(ContractModel):
    """Observação fora da pertinência ao alvo, com o motivo."""

    observation_id: Sha256Hex
    reason: M3Reason


class EvidenceAssessment(ContractModel):
    """Suficiência da evidência para a política/operação exatas do binding."""

    status: AssessmentStatus
    context_sha256: Sha256Hex
    policy_id: LocalId | None = None
    operation_id: str | None = None
    operation_version: str | None = None
    admissible_observation_ids: tuple[Sha256Hex, ...] = ()
    rejected: tuple[RejectedObservation, ...] = ()
    reasons: tuple[M3Reason, ...] = ()
    conflicts: tuple[tuple[Sha256Hex, ...], ...] = ()
    coverage: tuple[SelectorCoverage, ...] = ()
    action: RequiredAction = "none"
    version: Literal["1.0.0"] = ASSESSMENT_VERSION

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        """Suficiente não tem motivo; os demais estados têm motivo principal."""
        if (self.status == "sufficient") == bool(self.reasons):
            raise ValueError("suficiência sem motivos; demais estados com motivo principal")
        return self


class FieldAlternative(ContractModel):
    """Alternativa proposta para o alvo de ocorrência; não é aprovação nem escrita."""

    value: TypedValue
    state: Literal["present"] = "present"
    unit_state: Literal["not_applicable"] = "not_applicable"
    method: Literal["exact_recovery", "code_standardization"]
    evidence_refs: tuple[Sha256Hex, ...] = Field(min_length=1)
    transformation: str | None
    candidate_validation: CandidateValidation
    target_binding_id: LocalId
    target_set_name: NonEmptyText
    target_field_name: NonEmptyText
    target_scope: Literal["occurrence"] = "occurrence"
    would_modify_type: Literal[False] = False
    affected_elements: tuple[ElementRef, ...] = Field(min_length=1, max_length=1)
    requires_human_review: Literal[True] = True

    @model_validator(mode="after")
    def _validated(self) -> Self:
        """Só candidato validado como ``satisfied`` vira alternativa."""
        if self.candidate_validation.status != "satisfied":
            raise ValueError("alternativa exige candidato satisfeito pela validação IDS")
        if (self.method == "exact_recovery") != (self.transformation is None):
            raise ValueError(
                "recuperação exata não transforma; padronização declara a transformação"
            )
        return self


class FieldEnrichmentResult(ContractModel):
    """Resultado de um campo; abstenção e falha são resultados, não omissões."""

    field: FieldRef
    context_sha256: Sha256Hex | None
    assessment: EvidenceAssessment | None
    status: ResultStatus
    reason: M3Reason | None
    reasons: tuple[M3Reason, ...] = ()
    alternatives: tuple[FieldAlternative, ...] = ()
    limitations: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        """Exatamente uma alternativa só em ``proposed``; motivo coerente com o estado."""
        if self.status == "proposed":
            if len(self.alternatives) != 1 or self.reason is not None:
                raise ValueError("proposed exige exatamente uma alternativa e nenhum motivo")
            alternative = self.alternatives[0]
            if (
                alternative.target_set_name,
                alternative.target_field_name,
                alternative.target_binding_id,
                alternative.affected_elements,
            ) != (
                self.field.target_set_name,
                self.field.target_field_name,
                self.field.binding_id,
                (self.field.element,),
            ):
                raise ValueError("alternativa fora do alvo literal, binding ou elemento do campo")
            return self
        if (
            self.alternatives
            or self.reason is None
            or not self.reasons
            or self.reasons[0] != self.reason
        ):
            raise ValueError("estado sem proposta exige motivo principal e nenhuma alternativa")
        if self.status == "failed" and self.reason not in TECHNICAL_REASONS:
            raise ValueError("failed exige motivo técnico")
        if self.status == "unsupported" and self.reason not in UNSUPPORTED_REASONS:
            raise ValueError("unsupported exige motivo de capacidade")
        if self.status == "not_requested" and self.reason not in NOT_REQUESTED_REASONS:
            raise ValueError("not_requested exige motivo de não solicitação")
        return self


class EnrichmentIdentity(ContractModel):
    """Identidade do run M3: análise/diagnóstico exatos, condição, receita e bundle."""

    schema_version: SchemaVersionOne = 1
    enrichment_id: CanonicalUUID
    analysis_id: CanonicalUUID
    analysis_identity_sha256: Sha256Hex
    diagnostic_sha256: Sha256Hex
    condition_id: Literal["m1-e3-evidence-v1"] = CONDITION_ID
    condition_config_sha256: Sha256Hex
    recipe_sha256: Sha256Hex
    operation_bundle_sha256: Sha256Hex
    builder_version: Literal["1.0.0"] = BUILDER_VERSION
    catalog: CatalogReleaseRef | None
    pin_revision: int | None
    runtime: Literal["deterministic"] = "deterministic"
    input_sha256: Sha256Hex

    @model_validator(mode="after")
    def _input_hash(self) -> Self:
        """``input_sha256`` cobre todos os insumos (sem o ID do run e sem si próprio)."""
        body = self.model_dump(mode="json", exclude={"enrichment_id", "input_sha256"})
        if self.input_sha256 != canonical_sha256(body):
            raise ValueError("input_sha256 não corresponde aos insumos")
        return self


class EnrichmentProblem(ContractModel):
    """Falha técnica de um campo, preservada sem esconder os demais resultados."""

    code: NonEmptyText
    message: NonEmptyText
    requirement_key: str | None = None
    element_express_id: int | None = None


def _check_references(
    result: FieldEnrichmentResult, contexts: dict[str, FieldEvidenceContext]
) -> None:
    """Grafo interno do resultado resolve no próprio run (E3-06): hash correto não basta."""
    if result.context_sha256 is None:
        if result.assessment is not None or result.alternatives:
            raise ValueError("resultado sem contexto não tem avaliação nem alternativa")
        return
    context = contexts[result.context_sha256]
    if result.field != context.field:
        raise ValueError("campo do resultado difere do campo do contexto citado")
    assessment = result.assessment
    stale = result.status == "failed" and result.reason == "identity_mismatch"
    if assessment is not None and assessment.context_sha256 != result.context_sha256 and not stale:
        raise ValueError("avaliação de outro contexto")
    admissible = {r.observation_id for r in context.resolutions if r.admissible}
    if assessment is not None and not stale:
        resolved = {r.observation_id for r in context.resolutions}
        cited = {o for group in assessment.conflicts for o in group}
        if (
            not set(assessment.admissible_observation_ids) <= admissible
            or not {r.observation_id for r in assessment.rejected} <= resolved - admissible
            or not cited <= resolved
        ):
            raise ValueError("avaliação cita observação fora das resoluções do contexto")
    for alternative in result.alternatives:
        refs = set(alternative.evidence_refs)
        if assessment is None or not refs <= admissible & set(
            assessment.admissible_observation_ids
        ):
            raise ValueError("alternativa cita evidência fora das observações admitidas")


class EnrichmentRun(ContractModel):
    """Run M3 completo: resultados ordenados, contextos, problemas e hash do conteúdo."""

    schema_version: SchemaVersionOne = 1
    identity: EnrichmentIdentity
    state: Literal["completed", "failed"]
    results: tuple[FieldEnrichmentResult, ...]
    contexts: tuple[FieldEvidenceContext, ...]
    problems: tuple[EnrichmentProblem, ...] = ()
    content_sha256: Sha256Hex

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        """Ordem, unicidade, contextos citados e hash do conteúdo."""
        keys = [r.field.sort_key() for r in self.results]
        if keys != sorted(set(keys)):
            raise ValueError("resultados únicos e ordenados por campo")
        contexts = {c.context_sha256: c for c in self.contexts}
        if any(
            r.context_sha256 is not None and r.context_sha256 not in contexts for r in self.results
        ):
            raise ValueError("resultado cita contexto ausente")
        for result in self.results:
            _check_references(result, contexts)
        if any(r.field.analysis_id != self.identity.analysis_id for r in self.results):
            raise ValueError("resultado de outra análise")
        if self.content_sha256 != canonical_sha256(
            self.model_dump(mode="json", exclude={"content_sha256"})
        ):
            raise ValueError("content_sha256 não corresponde ao run")
        return self

    def counts(self) -> dict[str, int]:
        """Completude por estado de resultado."""
        found: dict[str, int] = {}
        for result in self.results:
            found[result.status] = found.get(result.status, 0) + 1
        return found


__all__ = [
    "RECIPE",
    "ContextRecipe",
    "EnrichmentIdentity",
    "EnrichmentRun",
    "EvidenceAssessment",
    "FieldAlternative",
    "FieldEnrichmentResult",
    "FieldEvidenceContext",
    "FieldRef",
    "M3Reason",
    "ObservedResolution",
    "RejectedObservation",
]
