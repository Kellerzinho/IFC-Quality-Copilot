"""Contratos do perfil Daiane na E4: transcrição do Apêndice B e reconciliação A/B (M1-04).

Estes formatos pertencem à E4 e ficam fora do pacote ``catalog-v1``: o inventário da
fonte tem campos (bloco, papel, dúvidas, continuação, eixos de disposição) que um
release não carrega. ``SourceAssertion`` só é usada quando a linha é representável sem
inventar categoria; o restante continua no inventário com motivo. Nada aqui aprova
conteúdo, cria binding ou decide equivalência: as decisões humanas são referenciadas
por ID e nunca fabricadas pelo carregador.
"""

import json
from collections.abc import Iterator
from itertools import pairwise
from typing import Annotated, Literal, Self

from pydantic import (
    Field,
    StrictBool,
    StrictInt,
    StringConstraints,
    field_validator,
    model_validator,
)

from src.domain_catalog.canonical import canonical_json_text, parse_json_strict
from src.domain_catalog.content import CatalogContent
from src.domain_catalog.models import (
    CatalogModel,
    FormatVersionOne,
    LocalId,
    NonEmptyText,
    PageNumber,
    Sha256Hex,
    SourceAssertion,
    SourceCategory,
    SourceRef,
    TranscriptionStatus,
)

APPENDIX_B_FORMAT = "ifcqc-daiane-b-transcription-1"
PROFILE_FORMAT = "ifcqc-daiane-profile-1"

SpecificationCode = Annotated[str, StringConstraints(pattern=r"^E(0[1-9]|10)$")]
"""Código de especificação do relatório IDS_Mestrado (E01–E10)."""

BRecordId = Annotated[str, StringConstraints(pattern=r"^dai2025:B-(DOC|E(0[1-9]|10))-\d{4}$")]
"""ID estável de registro B, fixado na primeira transcrição e nunca renumerado."""

Revision = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9._-]*$")]
IsoDate = Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}$")]
PositiveInt = Annotated[StrictInt, Field(ge=1)]
CountInt = Annotated[StrictInt, Field(ge=0)]

BRecordRole = Literal["specification_metadata", "applicability", "requirement", "unclassified"]
BBlock = Literal["cover", "header", "applicability", "requirements", "instructions"]
BBlockKind = Literal[
    "cover_line",
    "section_heading",
    "title",
    "description",
    "versions",
    "lead_in",
    "item",
    "heading",
    "text",
]
BTranscriptionState = Literal["transcribed", "transcribed_with_doubt", "redacted"]
ReviewKind = Literal[
    "assisted_extraction", "visual_check", "independent_second_check", "curator_check"
]
ReviewerKind = Literal["assistant", "human"]
ReviewOutcome = Literal["completed", "no_divergence", "divergences_found", "divergences_resolved"]
PASSING_OUTCOMES: frozenset[str] = frozenset({"no_divergence", "divergences_resolved"})
ContentOrigin = Literal["real_source", "synthetic_fixture"]


def _canonical_json(value: str) -> str:
    """Exige JSON canônico: o literal estruturado tem uma única forma em bytes."""
    if canonical_json_text(parse_json_strict(value)) != value:
        raise ValueError("literal estruturado precisa estar em JSON canônico")
    return value


CanonicalJson = Annotated[str, Field(min_length=2)]


class PageFurniture(CatalogModel):
    """Elemento repetido de página (cabeçalho corrente, numeração); não é requisito."""

    kind: Literal["running_header", "report_page_number", "page_number", "appendix_title"]
    literal: NonEmptyText


class BPage(CatalogModel):
    """Página do PDF inventariada, com os registros que começam ou continuam nela."""

    pdf_page: PageNumber
    printed_page: PageNumber | None
    report_page: str | None
    furniture: tuple[PageFurniture, ...] = ()
    record_ids: tuple[BRecordId, ...] = ()


class ExcludedPage(CatalogModel):
    """Página adjacente conferida e excluída do relatório, com o motivo."""

    pdf_page: PageNumber
    reason: NonEmptyText


class BSourceIdentity(CatalogModel):
    """Identidade do PDF lido e do intervalo do Apêndice B."""

    artifact_id: SourceRef
    pdf_sha256: Sha256Hex
    pdf_size_bytes: Annotated[StrictInt, Field(ge=1)]
    pdf_pages: tuple[PageNumber, PageNumber]
    printed_pages: tuple[PageNumber, PageNumber]
    excluded_pages: tuple[ExcludedPage, ...] = ()

    @model_validator(mode="after")
    def _ranges(self) -> Self:
        """Intervalos crescentes e de mesmo tamanho (página impressa ≠ página do PDF)."""
        first, last = self.pdf_pages
        printed_first, printed_last = self.printed_pages
        if first > last or printed_last - printed_first != last - first:
            raise ValueError("intervalos de páginas PDF/impressas incoerentes")
        return self


class TranscriptionReview(CatalogModel):
    """Passo de transcrição ou conferência efetivamente registrado.

    ``reviewer_kind`` é declaração local, não autenticação. ``curator_check`` só é aceito
    de ``human``; assistente nunca produz conferência de curador.
    """

    review_id: Revision
    kind: ReviewKind
    reviewer_kind: ReviewerKind
    reviewer_label: NonEmptyText
    date: IsoDate
    pdf_pages: tuple[PageNumber, PageNumber]
    outcome: ReviewOutcome
    notes: NonEmptyText
    evidence_ref: str | None = None

    @model_validator(mode="after")
    def _curator_is_human(self) -> Self:
        """Conferência de curador declarada por assistente é recusada."""
        if self.kind == "curator_check" and self.reviewer_kind != "human":
            raise ValueError("curator_check exige reviewer_kind human; assistente não confere")
        return self


class BSpecification(CatalogModel):
    """Especificação do relatório, com o título literal e as páginas que ocupa."""

    code: SpecificationCode
    title_literal: NonEmptyText
    pdf_pages: tuple[PageNumber, ...] = Field(min_length=1)


class BRecordLocator(CatalogModel):
    """Onde o registro está: páginas, bloco e posição na ordem da fonte."""

    pdf_pages: tuple[PageNumber, ...] = Field(min_length=1)
    printed_pages: tuple[PageNumber, ...] = Field(min_length=1)
    block: BBlock
    block_kind: BBlockKind
    order: PositiveInt
    source_lines: CountInt

    @model_validator(mode="after")
    def _pages_are_consecutive(self) -> Self:
        """Páginas consecutivas; impressa e PDF com o mesmo número de entradas."""
        pages = self.pdf_pages
        if any(b != a + 1 for a, b in pairwise(pages)):
            raise ValueError(f"pdf_pages não consecutivas: {pages}")
        if len(self.printed_pages) != len(pages):
            raise ValueError("printed_pages e pdf_pages com tamanhos diferentes")
        return self


class TranscriptionChange(CatalogModel):
    """Correção de transcrição: nova revisão, IDs preservados."""

    revision: Revision
    record_ids: tuple[BRecordId, ...] = Field(min_length=1)
    description: NonEmptyText


class AppendixBRecord(CatalogModel):
    """Unidade documental do Apêndice B, preservada mesmo quando não projetável.

    ``structured_json`` guarda, em JSON canônico, somente partes impressas (modalidade,
    faceta, nomes, tipo, operador e valor literais, instruções); chave ausente significa
    "não impresso", diferente de texto vazio ou ``"0"``. ``assertion`` é preenchida pelo
    carregador quando a categoria é declarada; o arquivo nunca a traz pronta.
    """

    id: BRecordId
    specification: SpecificationCode | None
    role: BRecordRole
    locator: BRecordLocator
    text_literal: NonEmptyText
    structured_json: CanonicalJson
    facet_literal: str | None = None
    category: SourceCategory | None = None
    transcription_state: BTranscriptionState
    transcription_status: TranscriptionStatus
    doubts: tuple[NonEmptyText, ...] = ()
    not_projectable_reason: NonEmptyText | None = None
    continuation_of: BRecordId | None = None
    assertion: SourceAssertion | None = None

    @field_validator("structured_json")
    @classmethod
    def _structured_is_canonical(cls, value: str) -> str:
        """O literal estruturado é JSON canônico de um objeto."""
        _canonical_json(value)
        if not isinstance(parse_json_strict(value), dict):
            raise ValueError("literal estruturado precisa ser um objeto JSON")
        return value

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        """Prefixo do ID, categoria versus motivo, dúvidas versus estado, continuação."""
        scope = self.id.split(":B-")[1].split("-")[0]
        if scope != (self.specification or "DOC"):
            raise ValueError(
                f"prefixo do ID {self.id} difere da especificação {self.specification}"
            )
        if self.role in ("applicability", "requirement") and self.specification is None:
            raise ValueError(f"papel {self.role} exige especificação")
        if (self.category is None) == (self.not_projectable_reason is None):
            raise ValueError(
                "registro sem categoria exige not_projectable_reason, e com categoria não admite"
            )
        if self.transcription_state != "transcribed" and not self.doubts:
            raise ValueError(f"estado {self.transcription_state} exige dúvidas/justificativa")
        if self.transcription_state == "transcribed" and self.doubts:
            raise ValueError("registro com dúvidas precisa de estado transcribed_with_doubt")
        if self.continuation_of is not None and self.category is not None:
            raise ValueError("continuação não é projetada: o registro principal já a representa")
        if self.assertion is not None and (self.category is None or self.assertion.id != self.id):
            raise ValueError("assertiva só para registro com categoria e com o mesmo ID")
        return self

    @property
    def structured(self) -> dict[str, object]:
        """Cópia nova do literal estruturado."""
        value = json.loads(self.structured_json)
        if not isinstance(value, dict):
            raise TypeError(f"{self.id}: literal estruturado não é objeto JSON")
        return value


class AppendixBInventory(CatalogModel):
    """Transcrição revisada do Apêndice B com inventário de páginas, blocos e registros."""

    format: Literal["ifcqc-daiane-b-transcription-1"]
    format_version: FormatVersionOne
    revision: Revision
    content_origin: ContentOrigin
    source: BSourceIdentity
    method: NonEmptyText
    reviews: tuple[TranscriptionReview, ...] = ()
    specifications: tuple[BSpecification, ...]
    pages: tuple[BPage, ...]
    records: tuple[AppendixBRecord, ...]
    changes: tuple[TranscriptionChange, ...] = ()

    def record(self, record_id: str) -> AppendixBRecord:
        """Registro pelo ID estável."""
        for item in self.records:
            if item.id == record_id:
                return item
        raise KeyError(record_id)

    def iter_primary(self) -> Iterator[AppendixBRecord]:
        """Registros que não são continuação (os que entram nos totais)."""
        return (record for record in self.records if record.continuation_of is None)


class AppendixBTotals(CatalogModel):
    """Totais derivados da transcrição; nunca declarados à mão."""

    records: CountInt
    continuations: CountInt
    by_role: dict[str, int]
    by_specification_role: dict[str, dict[str, int]]
    by_facet: dict[str, int]
    by_modality: dict[str, int]
    projected_assertions: CountInt
    not_projected: CountInt
    with_doubt: CountInt
    redacted: CountInt


# --- Perfil E4 e reconciliação A/B ------------------------------------------------------

FamilyId = Annotated[str, StringConstraints(pattern=r"^A([1-9]|10)$")]
ReasonCode = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$")]
CorrespondenceId = Annotated[str, StringConstraints(pattern=r"^ab-\d{4}$")]
DivergenceId = Annotated[
    str, StringConstraints(pattern=r"^(dai2025:A\d+-[A-Z0-9]+#\d+|ab-div-\d{4})$")
]
Destination = Literal["candidate", "pending", "outside_semantic_scope"]


def _no_repeats(owner: str, **sets: tuple[str, ...]) -> None:
    """Conjuntos de IDs/campos não admitem repetição (identidade canônica estável)."""
    for name, values in sets.items():
        if len(values) != len(set(values)):
            raise ValueError(f"{owner}: valor repetido em {name}")


CatalogAxisState = Literal["candidate_draft", "not_registered", "outside_scope"]
CapabilityAxisState = Literal[
    "not_evaluated", "unsupported", "verified_for_case", "real_model_verified"
]
ABRelation = Literal[
    "same_claim",
    "same_printed_target",
    "different_claim",
    "unresolved",
    "not_present_in_other_source",
]
"""``same_claim`` afirma a mesma exigência, inclusive domínio/restrições comparados;
``same_printed_target`` só afirma o mesmo alvo impresso (família/especificação, faceta,
nomes e tipo quando comparados), com domínio e restrições ainda não comparados."""
ReviewState = Literal["assistant_proposal", "human_decided"]


class DispositionAxes(CatalogModel):
    """Eixos separados: transcrição, cadastro, validação e enriquecimento."""

    transcription: TranscriptionStatus
    catalog: CatalogAxisState
    validation: CapabilityAxisState
    enrichment: CapabilityAxisState
    validation_reason: NonEmptyText
    enrichment_reason: NonEmptyText


class ProfileDisposition(CatalogModel):
    """Destino de um registro A ou B; fonte sem projeção fica ``pending`` e nunca some."""

    source_record_id: SourceRef
    source_kind: Literal["A", "B"]
    family_id: FamilyId | None
    category: SourceCategory | None
    destination: Destination
    reason_code: ReasonCode
    reason: NonEmptyText
    candidate_ids: tuple[LocalId, ...] = ()
    decision_ids: tuple[LocalId, ...] = ()
    correspondence_ids: tuple[CorrespondenceId, ...] = ()
    axes: DispositionAxes

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        """Candidato cita entidades; pendência e fora de escopo não cadastram nada."""
        if self.destination == "candidate" and not self.candidate_ids:
            raise ValueError("destino candidate exige candidate_ids")
        if self.destination != "candidate" and self.candidate_ids:
            raise ValueError(f"destino {self.destination} não admite candidate_ids")
        expected = {
            "candidate": "candidate_draft",
            "pending": "not_registered",
            "outside_semantic_scope": "outside_scope",
        }[self.destination]
        if self.axes.catalog != expected:
            raise ValueError(f"destino {self.destination} exige eixo catalog {expected}")
        _no_repeats(
            self.source_record_id,
            candidate_ids=self.candidate_ids,
            decision_ids=self.decision_ids,
            correspondence_ids=self.correspondence_ids,
        )
        return self


class ABCorrespondence(CatalogModel):
    """Relação A↔B (1:N, N:1); proposta do assistente até decisão humana registrada.

    ``compared_fields`` declara o alcance demonstrado; ``same_claim`` exige um campo
    ``domain…`` comparado, senão a relação conservadora é ``same_printed_target``.
    """

    id: CorrespondenceId
    a_record_ids: tuple[SourceRef, ...] = ()
    b_record_ids: tuple[BRecordId, ...] = ()
    relation: ABRelation
    justification: NonEmptyText
    compared_fields: tuple[NonEmptyText, ...] = ()
    review_state: ReviewState
    decision_ids: tuple[LocalId, ...] = ()

    @model_validator(mode="after")
    def _sides(self) -> Self:
        """Ausente na outra fonte tem um só lado; demais relações, os dois."""
        sides = (bool(self.a_record_ids), bool(self.b_record_ids))
        if self.relation == "not_present_in_other_source":
            if sides not in ((True, False), (False, True)):
                raise ValueError("not_present_in_other_source exige exatamente um lado")
        elif sides != (True, True):
            raise ValueError(f"relação {self.relation} exige registros A e B")
        if self.review_state == "human_decided" and not self.decision_ids:
            raise ValueError("correspondência decidida exige decision_ids")
        _no_repeats(
            self.id,
            a_record_ids=self.a_record_ids,
            b_record_ids=self.b_record_ids,
            compared_fields=self.compared_fields,
            decision_ids=self.decision_ids,
        )
        if self.relation == "same_claim" and not any(
            field.startswith("domain") for field in self.compared_fields
        ):
            raise ValueError(
                "same_claim exige domínio/restrições comparados (campo domain…); com alcance "
                "menor use same_printed_target"
            )
        return self


class DivergenceEntry(CatalogModel):
    """Divergência aberta: achado da matriz (já relatado) ou comparação A/B (nova)."""

    id: DivergenceId
    origin: Literal["matrix_finding", "ab_comparison"]
    reported_before: StrictBool
    source_record_ids: tuple[SourceRef, ...] = Field(min_length=1)
    text: NonEmptyText
    status: Literal["open"] = "open"
    decision_ids: tuple[LocalId, ...] = ()

    @model_validator(mode="after")
    def _sets(self) -> Self:
        """Registros e decisões citados sem repetição."""
        _no_repeats(
            self.id, source_record_ids=self.source_record_ids, decision_ids=self.decision_ids
        )
        return self


class IdentityEntry(CatalogModel):
    """Identidade persistida de candidato: reuso E1 ou UUID alocado na E4."""

    local_id: LocalId
    entity_kind: NonEmptyText
    key: NonEmptyText
    origin: Literal["e1_reused", "e4_allocated"]


class DecisionReference(CatalogModel):
    """Decisão já registrada por Felipe, citada por documento; o carregador não a cria."""

    ref: NonEmptyText
    date: IsoDate
    summary: NonEmptyText
    document: NonEmptyText


class HistoricalCount(CatalogModel):
    """Contagem com seu denominador próprio; não é somada a outras."""

    label: NonEmptyText
    value: NonEmptyText
    denominator: NonEmptyText
    source: NonEmptyText
    status: Literal["not_reconciled", "reconciled"]


class FamilyMapping(CatalogModel):
    """Família A e especificação B que imprimem a mesma classe (proposta do assistente)."""

    family_id: FamilyId
    specification: SpecificationCode
    justification: NonEmptyText


class ProfileBases(CatalogModel):
    """Bases exatas da reconciliação: matriz A, transcrição B e candidatos."""

    matrix_revision: NonEmptyText
    matrix_sha256: Sha256Hex
    appendix_b_revision: Revision
    appendix_b_sha256: Sha256Hex
    pdf_sha256: Sha256Hex
    candidates_content_sha256: Sha256Hex


class ProfileReconciliation(CatalogModel):
    """Documento declarativo de reconciliação; o build valida, não cria decisões."""

    format: Literal["ifcqc-daiane-profile-1"]
    format_version: FormatVersionOne
    revision: Revision
    bases: ProfileBases
    method: NonEmptyText
    family_map: tuple[FamilyMapping, ...]
    dispositions: tuple[ProfileDisposition, ...]
    correspondences: tuple[ABCorrespondence, ...]
    divergences: tuple[DivergenceEntry, ...]
    identities: tuple[IdentityEntry, ...]
    decisions: tuple[DecisionReference, ...] = ()
    historical_counts: tuple[HistoricalCount, ...] = ()
    pending_sources: tuple[NonEmptyText, ...] = ()

    @model_validator(mode="after")
    def _unique_keys(self) -> Self:
        """Mapa de famílias e decisões com chave única; fontes pendentes sem repetição."""
        _no_repeats(
            "reconciliação",
            family_map=tuple(m.family_id for m in self.family_map),
            family_map_specifications=tuple(m.specification for m in self.family_map),
            decisions=tuple(d.ref for d in self.decisions),
            pending_sources=self.pending_sources,
        )
        return self


CapabilityClassifier = Literal["synthetic_contract", "real_model"]


class CapabilityCaseManifest(CatalogModel):
    """Caso efetivamente executado que sustenta uma capacidade, com hashes dos artefatos."""

    case_id: NonEmptyText
    nodeid: NonEmptyText
    outcome: Literal["passed", "failed", "skipped", "not_executed"]
    exit_code: StrictInt
    test_file: NonEmptyText
    test_file_sha256: Sha256Hex
    implementation_file: NonEmptyText
    implementation_sha256: Sha256Hex
    raw_report_file: NonEmptyText
    raw_report_sha256: Sha256Hex
    inputs_file: NonEmptyText
    inputs_sha256: Sha256Hex
    classifier: CapabilityClassifier
    capability_cell: NonEmptyText | None = None
    """Célula da matriz IDS E3 exercitada pelo caso (``requirement:property:literal`` etc.)."""
    binding_id: LocalId
    binding_sha256: Sha256Hex
    """Binding efetivamente exercitado pelo caso; o caso só sustenta afirmações sobre ele."""


class CapabilityClaim(CatalogModel):
    """Afirmação de capacidade de um binding para um caso; só vale com evidência conferida.

    Validação exige ``capability_cell`` (célula da matriz IDS E3 que o caso exercitou);
    enriquecimento não a usa, porque é conferido contra o bundle de operações.
    """

    binding_id: LocalId
    binding_sha256: Sha256Hex
    policy_sha256: Sha256Hex | None = None
    base_a_sha256: Sha256Hex
    base_b_sha256: Sha256Hex
    axis: Literal["validation", "enrichment"]
    ifc_schema: NonEmptyText
    facet: NonEmptyText
    carrier_kind: NonEmptyText
    capability_cell: NonEmptyText | None = None
    operation_id: str | None = None
    operation_version: str | None = None
    case_id: NonEmptyText

    @model_validator(mode="after")
    def _cell_matches_axis(self) -> Self:
        """Validação cita a célula IDS; enriquecimento não a declara."""
        if (self.axis == "validation") != (self.capability_cell is not None):
            raise ValueError(
                "capability_cell é obrigatória em validação e não se aplica a enriquecimento"
            )
        return self


class ProfileCapabilityEvidence(CatalogModel):
    """Evidência local de capacidade, com bytes fornecidos explicitamente pelo chamador.

    O builder recalcula os hashes dos bytes em ``artifacts`` e nunca segue caminhos ou
    URLs citados. ``operation_manifest_json`` é o manifesto que o chamador diz ter
    carregado; ele só vale se o hash coincidir com a âncora ``CapabilityTrust`` calculada
    fora desta evidência. Hash comprova consistência, não autoria.
    """

    cases: tuple[CapabilityCaseManifest, ...] = ()
    claims: tuple[CapabilityClaim, ...] = ()
    artifacts: dict[str, bytes] = Field(default_factory=dict)
    operation_manifest_json: str | None = None


class CapabilityTrust(CatalogModel):
    """Âncoras de confiança fornecidas separadamente da evidência.

    ``approved_nodeids`` é a lista de casos aceitos como evidência; ``operation_bundle_
    manifest_sha256`` deve ser calculado pelo código a partir do bundle E3 efetivamente
    carregado (``build_e3_operation_bundle().manifest_sha256``); ``ids_capability_
    manifest_sha256`` é o hash da matriz IDS E3 carregada (``CAPABILITY_MANIFEST_SHA256``
    de ``src.validation.ids_constraints``); ``approved_implementation_sha256s`` e
    ``executed_report_sha256s`` são hashes da implementação e do relatório bruto
    calculados por quem executou os casos; ``real_model_input_sha256s`` lista os insumos
    reconhecidos como modelo real. Sem âncora, nenhuma afirmação é aceita e
    ``real_model`` declarado não basta. Âncora é consistência entre artefatos fornecidos
    separadamente, não assinatura nem prova criptográfica de execução.
    """

    approved_nodeids: tuple[NonEmptyText, ...] = ()
    operation_bundle_manifest_sha256: Sha256Hex | None = None
    ids_capability_manifest_sha256: Sha256Hex | None = None
    approved_implementation_sha256s: tuple[Sha256Hex, ...] = ()
    executed_report_sha256s: tuple[Sha256Hex, ...] = ()
    real_model_input_sha256s: tuple[Sha256Hex, ...] = ()


class VerifiedCapability(CatalogModel):
    """Capacidade conferida para um caso: nunca suporte universal."""

    binding_id: LocalId
    axis: Literal["validation", "enrichment"]
    state: Literal["verified_for_case", "real_model_verified"]
    case_id: NonEmptyText
    nodeid: NonEmptyText
    classifier: CapabilityClassifier
    capability_cell: NonEmptyText | None = None


class DaianeProfileInventory(CatalogModel):
    """Perfil validado: reconciliação, candidatos em rascunho e capacidades conferidas."""

    reconciliation: ProfileReconciliation
    reconciliation_sha256: Sha256Hex
    candidates: CatalogContent
    a_record_ids: tuple[SourceRef, ...]
    a_categories: dict[str, str]
    b_inventory: AppendixBInventory
    matrix_divergence_items: CountInt
    matrix_divergence_records: CountInt
    verified_capabilities: tuple[VerifiedCapability, ...] = ()


class ProfileReport(CatalogModel):
    """Relatório do perfil: inventário, cadastro e capacidades em estados separados.

    ``source_coverage_complete`` da E1 não é reutilizado com sentido novo.
    """

    reconciliation_revision: Revision
    reconciliation_sha256: Sha256Hex
    candidates_content_sha256: Sha256Hex
    a_total: CountInt
    a_alphanumeric: CountInt
    a_auxiliary: CountInt
    b_total: CountInt
    b_by_role: dict[str, int]
    inventory_accounted_for: StrictBool
    appendix_b_transcription_complete: StrictBool
    appendix_b_research_checked: StrictBool
    appendix_b_check_level: Literal["not_checked", "assistant_only", "includes_human", "curator"]
    """Quem declarou as conferências: ``assistant_only`` não é curadoria nem revisão humana."""
    domain_review_complete: StrictBool
    original_instrument_equivalence_verified: StrictBool
    profile_operational: StrictBool
    by_destination: dict[str, dict[str, int]]
    by_family_destination: dict[str, dict[str, int]]
    by_axis: dict[str, dict[str, int]]
    pending_by_reason: dict[str, int]
    correspondences_by_relation: dict[str, int]
    correspondences_by_review_state: dict[str, int]
    divergences: dict[str, int]
    matrix_divergence_items: CountInt
    matrix_divergence_records: CountInt
    historical_counts: tuple[HistoricalCount, ...]
    verified_capabilities: tuple[VerifiedCapability, ...] = ()
    pending_sources: tuple[NonEmptyText, ...] = ()
    human_gates: tuple[NonEmptyText, ...] = ()
