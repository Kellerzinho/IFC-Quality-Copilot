"""Snapshot formal IDS: requisitos, resultados, cobertura, problemas e observações (M2).

Cinco estados formais: ``compliant``, ``non_compliant``, ``not_applicable``,
``not_verified`` e ``error``. ``ExpectedField`` é o que o IDS exige (nunca
observação). Toda linha de requisito declarado fica no inventário, inclusive com
população zero, catálogo indisponível ou faceta recusada; linhas de escopo usam
``element=None`` em vez de elemento fictício. Denominador desconhecido é ``None``,
não zero. ``content_sha256`` cobre o conteúdo sem ``snapshot_id``, instante de
criação e o próprio hash; o anexo semântico do catálogo é separado e nunca altera
estado formal, esperado ou observado.
"""

from typing import Annotated, Literal, Self

from pydantic import Field, StrictBool, StrictInt, model_validator

from src.domain_catalog.contracts import (
    BindingRequest,
    CatalogReleaseRef,
    ContractModel,
    PredefinedTypeContext,
    ResolutionResult,
)
from src.domain_catalog.models import NonEmptyText, Sha256Hex
from src.domain_catalog.package import UtcTimestamp
from src.ifc_analyzer.identity import ElementRef
from src.ifc_analyzer.observations import SearchReport
from src.operations.contracts import CanonicalUUID, SchemaVersionOne, canonical_sha256
from src.translator.ids_document import (
    IDSDocument,
    IDSLocation,
    IDSValue,
    SpecificationCardinality,
)
from src.validation.analysis_identity import AnalysisIdentity, CatalogState

FormalState = Literal["compliant", "non_compliant", "not_applicable", "not_verified", "error"]
NonNegative = Annotated[StrictInt, Field(ge=0)]


class RequirementRef(IDSLocation):
    """Localizador de faceta de requisito (hash do IDS e índices originais)."""

    @model_validator(mode="after")
    def _requirement_section(self) -> Self:
        """Somente seção ``requirements``; aplicabilidade não se finge requisito."""
        if self.section != "requirements":
            raise ValueError("RequirementRef exige seção requirements")
        return self


class ExpectedField(ContractModel):
    """Exigência literal do IDS para um requisito; nunca valor observado."""

    requirement: RequirementRef
    facet_tag: NonEmptyText
    set_name: IDSValue | None
    field_name: IDSValue | None
    data_type: str | None
    cardinality: NonEmptyText
    cardinality_origin: Literal["explicit", "schema_default"]
    value: IDSValue | None
    fragment: str
    fragment_sha256: Sha256Hex

    def digest(self) -> str:
        """Hash canônico do esperado (referenciado pelas linhas de resultado)."""
        return canonical_sha256(self.model_dump(mode="json"))


class SemanticAnnotation(ContractModel):
    """Anexo do catálogo a uma linha formal; nunca altera o estado IDS."""

    state: Literal["resolved", "unresolved", "unavailable"]
    request: BindingRequest | None = None
    predefined_type: PredefinedTypeContext | None = None
    resolution: ResolutionResult | None = None
    catalog: CatalogReleaseRef | None = None
    error_reason: str | None = None
    limitations: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        """Resolvido exige resolução; indisponível exige motivo."""
        if self.state in ("resolved", "unresolved") and self.resolution is None:
            raise ValueError("anexo resolvido/não resolvido exige a resolução real")
        if self.state == "unavailable" and self.error_reason is None:
            raise ValueError("anexo indisponível exige motivo")
        return self


class RequirementResult(ContractModel):
    """Resultado formal de um requisito para um elemento, ou linha de escopo sem elemento."""

    analysis_id: CanonicalUUID
    requirement: RequirementRef
    expected_sha256: Sha256Hex
    element: ElementRef | None
    state: FormalState
    reason: str | None
    backend_passed: StrictBool | None = None
    backend_detail: str | None = None
    search_report_sha256: Sha256Hex | None = None
    observation_ids: tuple[Sha256Hex, ...] = ()
    capability_cell: NonEmptyText
    annotation: SemanticAnnotation | None = None

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        """Estados avaliados exigem elemento e resultado do backend; recusas exigem motivo."""
        if self.state in ("compliant", "non_compliant"):
            if self.element is None or self.backend_passed is None:
                raise ValueError("estado avaliado exige elemento e resultado do backend")
            if self.backend_passed != (self.state == "compliant"):
                raise ValueError("estado avaliado precisa refletir o resultado do backend")
            if self.state == "compliant" and self.reason is not None:
                raise ValueError("compliant não tem motivo de recusa")
            if self.state == "non_compliant" and self.reason != "requirement_violated":
                raise ValueError("non_compliant usa o motivo requirement_violated")
        elif self.reason is None:
            raise ValueError(f"{self.state} exige motivo explícito")
        return self

    def sort_key(self) -> tuple[int, int, int]:
        """Ordem: especificação, requisito, elemento (linha de escopo primeiro)."""
        return (
            self.requirement.specification_index,
            self.requirement.index,
            0 if self.element is None else self.element.express_id,
        )


class SpecificationResult(ContractModel):
    """Especificação: cardinalidade, população e status agregado de todos os estados."""

    analysis_id: CanonicalUUID
    specification_index: NonNegative
    name: str
    identifier: str | None
    cardinality: SpecificationCardinality
    population_state: Literal["known", "undetermined"]
    members: tuple[ElementRef, ...]
    member_count: NonNegative | None
    cardinality_evaluation: Literal["satisfied", "violated", "not_evaluated"]
    status: Literal["satisfied", "violated", "not_verified", "error"]
    reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        """População conhecida tem membros e contagem; indeterminada não tem nenhum."""
        if self.population_state == "known":
            if self.member_count != len(self.members):
                raise ValueError("contagem difere dos membros conhecidos")
        elif self.members or self.member_count is not None:
            raise ValueError("população indeterminada não tem membros nem contagem")
        elif self.cardinality_evaluation != "not_evaluated":
            raise ValueError("população indeterminada não avalia cardinalidade")
        return self


class CoverageSummary(ContractModel):
    """Cobertura separando escopo de especificação e pares elemento/requisito."""

    specifications: NonNegative
    declared_requirements: NonNegative
    undetermined_specifications: NonNegative
    known_pairs: NonNegative | None
    evaluated_pairs: NonNegative
    refused_pairs: NonNegative
    error_pairs: NonNegative
    not_applicable_pairs: NonNegative
    scope_rows: NonNegative


class TechnicalProblem(ContractModel):
    """Problema técnico ou semântico correlacionado a especificação/requisito/elemento."""

    code: NonEmptyText
    message: NonEmptyText
    specification_index: NonNegative | None = None
    location_key: str | None = None
    element: ElementRef | None = None


class ElementContext(ContractModel):
    """Fatos do elemento lidos pelo M2 para o catálogo (PredefinedType e leituras)."""

    element: ElementRef
    predefined_type: PredefinedTypeContext


class SourceCheck(ContractModel):
    """Hashes das fontes e assinatura estrutural antes/depois da avaliação."""

    ifc_sha256: Sha256Hex
    ids_sha256: Sha256Hex
    signature_before: Sha256Hex
    signature_after: Sha256Hex
    entity_count: NonNegative

    @model_validator(mode="after")
    def _unchanged(self) -> Self:
        """Só existe snapshot de fonte não mutada."""
        if self.signature_before != self.signature_after:
            raise ValueError("assinatura mudou: fonte mutada não produz snapshot")
        return self


_METADATA = frozenset({"snapshot_id", "created_at_utc", "content_sha256"})


class DiagnosticSnapshot(ContractModel):
    """Diagnóstico formal imutável de uma análise, com hash de conteúdo sem autorreferência."""

    schema_version: SchemaVersionOne = 1
    snapshot_id: CanonicalUUID
    created_at_utc: UtcTimestamp
    identity: AnalysisIdentity
    ids_document: IDSDocument
    ifc_schema: NonEmptyText
    expected_fields: tuple[ExpectedField, ...]
    specifications: tuple[SpecificationResult, ...]
    requirements: tuple[RequirementResult, ...]
    search_reports: tuple[SearchReport, ...]
    element_contexts: tuple[ElementContext, ...] = ()
    coverage: CoverageSummary
    problems: tuple[TechnicalProblem, ...]
    catalog_runtime_state: CatalogState
    source_check: SourceCheck
    content_sha256: Sha256Hex

    def content_digest(self) -> str:
        """Hash do conteúdo, excluindo metadados e o próprio hash."""
        return snapshot_digest(self.model_dump(mode="json"))

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        """Hash, referências internas e identidade coerentes."""
        if self.content_sha256 != self.content_digest():
            raise ValueError("content_sha256 não corresponde ao conteúdo")
        if self.ids_document.ids_sha256 != self.identity.ids.sha256:
            raise ValueError("IDS do snapshot difere da identidade")
        if self.source_check.ifc_sha256 != self.identity.ifc.sha256:
            raise ValueError("IFC do snapshot difere da identidade")
        expected = {item.requirement.key(): item.digest() for item in self.expected_fields}
        reports = {report.report_sha256 for report in self.search_reports}
        analysis = self.identity.analysis_id
        for row in self.requirements:
            if row.analysis_id != analysis:
                raise ValueError("linha de outra análise")
            if expected.get(row.requirement.key()) != row.expected_sha256:
                raise ValueError("linha sem esperado correspondente")
            if row.search_report_sha256 is not None and row.search_report_sha256 not in reports:
                raise ValueError("linha cita relatório de busca ausente")
        if any(s.analysis_id != analysis for s in self.specifications):
            raise ValueError("especificação de outra análise")
        keys = [row.sort_key() for row in self.requirements]
        if keys != sorted(keys):
            raise ValueError("linhas fora da ordem canônica")
        ids = [context.element.express_id for context in self.element_contexts]
        if ids != sorted(set(ids)):
            raise ValueError("contextos de elemento únicos e ordenados")
        if any(
            context.element.sha256 != self.identity.ifc.sha256 for context in self.element_contexts
        ):
            raise ValueError("contexto de elemento de outra fonte")
        return self

    def context_for(self, element: ElementRef) -> PredefinedTypeContext | None:
        """PredefinedType do elemento conforme lido pelo M2, se registrado."""
        return next(
            (c.predefined_type for c in self.element_contexts if c.element == element), None
        )

    def expected_for(self, row: RequirementResult) -> ExpectedField:
        """Esperado da linha."""
        return next(e for e in self.expected_fields if e.requirement.key() == row.requirement.key())

    def report_for(self, row: RequirementResult) -> SearchReport:
        """Relatório de busca usado pelos gates da linha."""
        return next(r for r in self.search_reports if r.report_sha256 == row.search_report_sha256)

    def with_annotations(
        self,
        requirements: tuple[RequirementResult, ...],
        catalog_runtime_state: CatalogState,
        problems: tuple[TechnicalProblem, ...],
    ) -> "DiagnosticSnapshot":
        """Cópia com anexos semânticos; o conteúdo formal das linhas não pode mudar."""
        for old, new in zip(self.requirements, requirements, strict=True):
            if old.model_dump(exclude={"annotation"}) != new.model_dump(exclude={"annotation"}):
                raise ValueError("anexo semântico não pode alterar resultado formal")
        data = {
            **self.model_dump(mode="json"),
            "requirements": [row.model_dump(mode="json") for row in requirements],
            "catalog_runtime_state": catalog_runtime_state,
            "problems": [problem.model_dump(mode="json") for problem in problems],
        }
        return DiagnosticSnapshot.model_validate({**data, "content_sha256": snapshot_digest(data)})


def snapshot_digest(document: dict[str, object]) -> str:
    """Hash de conteúdo de um snapshot em forma JSON, sem metadados nem o próprio hash."""
    return canonical_sha256({k: v for k, v in document.items() if k not in _METADATA})
