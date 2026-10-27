"""Registros, comandos e recibos da curadoria e da publicação do catálogo (E2).

Os eixos ficam separados (plano M1 §4.2): solicitação, rascunho, validação, revisão,
aprovação, candidato e publicação têm registros e estados próprios. A aprovação se
liga a uma revisão exata do rascunho (número e SHA-256 do conteúdo); a publicação, a
um candidato exato (versão e SHA-256 do manifesto). Toda mudança grava evento e
recibo na mesma transação; recibo de salvamento (``CommitReceipt``), aprovação de
conteúdo (``ReviewRecord``) e publicação (``PublicationReceipt``) são distintos.
Nenhum registro aqui autentica pessoas: o ator é a identificação informada.
"""

import hashlib
from dataclasses import dataclass
from typing import Annotated, Any, Generic, Literal, Self, TypeVar

from pydantic import Field, StrictInt, StringConstraints, model_validator

from src.domain_catalog.actor import ActorSnapshot
from src.domain_catalog.canonical import canonical_json_bytes
from src.domain_catalog.content import ENTITY_KINDS, CatalogContent, EntityKind
from src.domain_catalog.contracts import CatalogReleaseRef, ContractModel, RequestFacet
from src.domain_catalog.models import IfcSchemaId, LocalId, NonEmptyText, Sha256Hex
from src.domain_catalog.package import (
    CatalogIdentity,
    ComponentTerms,
    ContentOrigin,
    UtcTimestamp,
)

CommandId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{3,127}$")]
"""Chave idempotente gerada por quem envia o comando (por exemplo, um UUID)."""

PositiveInt = Annotated[StrictInt, Field(ge=1)]
CountInt = Annotated[StrictInt, Field(ge=0)]

LIFECYCLE_KINDS: tuple[EntityKind, ...] = (
    "concepts",
    "units",
    "value_sets",
    "applicability_rules",
    "evidence_policies",
    "bindings",
    "aliases",
    "profile_memberships",
)
"""Tipos com estado cadastral (``lifecycle``); fontes e decisões não têm."""

LifecycleKind = Literal[
    "concepts",
    "units",
    "value_sets",
    "applicability_rules",
    "evidence_policies",
    "bindings",
    "aliases",
    "profile_memberships",
]


def content_sha256(content: CatalogContent) -> str:
    """SHA-256 do conteúdo em JSON canônico, com as entidades de cada tipo ordenadas por ID.

    É a identidade do conteúdo de uma revisão de rascunho; a ordem de inserção não
    muda o hash, qualquer alteração de dado muda.
    """
    document = {
        kind: sorted(
            (entity.model_dump(mode="json") for entity in getattr(content, kind)),
            key=lambda item: str(item["id"]),
        )
        for kind in ENTITY_KINDS
    }
    return hashlib.sha256(canonical_json_bytes(document)).hexdigest()


class CommandMeta(ContractModel):
    """Envelope mínimo de um comando: chave idempotente e referência do ator.

    O ator chega por referência (``actor_context_id``) e é resgatado no backend; o
    comando nunca carrega papel, nome ou garantia escritos pela interface.
    """

    command_id: CommandId
    actor_context_id: NonEmptyText


# --- Solicitações -----------------------------------------------------------------------

RequestState = Literal["open", "in_triage", "in_review", "approved", "rejected", "cancelled"]
"""Estados da solicitação (plano M1 §4.2): aberta, em triagem, em revisão, aprovada,
rejeitada, cancelada. Aprovada significa que o rascunho que a atende foi aprovado; a
publicação é registrada à parte (``published_release``)."""

TERMINAL_REQUEST_STATES: frozenset[str] = frozenset({"rejected", "cancelled"})


class RequestedField(ContractModel):
    """Campo pedido como o requisito o escreve; desconhecido fica ``None``."""

    ifc_schema: IfcSchemaId | None = None
    facet: RequestFacet | None = None
    entity: NonEmptyText | None = None
    set_name: NonEmptyText | None = None
    field_name: NonEmptyText


class OriginRef(ContractModel):
    """Referência à origem da solicitação, sem copiar conteúdo do IFC ou do IDS."""

    kind: Literal["ids_requirement", "ifc_element", "analysis", "document", "other"]
    ref: NonEmptyText
    note: str | None = None


class ChangeRequest(ContractModel):
    """Pedido de cadastro ou mapeamento; não altera release, IDS nem IFC."""

    request_id: LocalId
    catalog_id: LocalId
    state: RequestState
    motivation: NonEmptyText
    field: RequestedField
    origin_refs: tuple[OriginRef, ...] = ()
    requested_by: ActorSnapshot
    requested_at: UtcTimestamp
    draft_id: LocalId | None = None
    published_release: CatalogReleaseRef | None = None
    closing_reason: str | None = None


# --- Rascunhos e revisões ---------------------------------------------------------------

DraftState = Literal[
    "editing", "in_review", "approved", "publishing", "published", "rejected", "cancelled"
]
"""Estados do rascunho. ``publishing`` trava edições enquanto há intenção de publicação."""

TERMINAL_DRAFT_STATES: frozenset[str] = frozenset({"published", "rejected", "cancelled"})
_APPROVAL_STATES: frozenset[str] = frozenset({"approved", "publishing", "published"})

RevisionOrigin = Literal["empty", "base_release", "import", "human_edit", "assistant_proposal"]
"""De onde veio o conteúdo de uma revisão; proposta de assistente fica identificada."""


class DraftRecord(ContractModel):
    """Rascunho de um catálogo: estado, revisão atual e aprovação vigente, se houver."""

    draft_id: LocalId
    catalog: CatalogIdentity
    title: NonEmptyText
    state: DraftState
    current_revision: PositiveInt
    base_release: CatalogReleaseRef | None = None
    approval_id: LocalId | None = None
    candidate_id: LocalId | None = None
    published_release: CatalogReleaseRef | None = None
    created_by: ActorSnapshot
    created_at: UtcTimestamp
    updated_at: UtcTimestamp
    closing_reason: str | None = None

    @model_validator(mode="after")
    def _approval_matches_state(self) -> Self:
        """Aprovação vigente só em rascunho aprovado; release publicado só se publicado."""
        if (self.approval_id is not None) != (self.state in _APPROVAL_STATES):
            raise ValueError(f"estado {self.state} incompatível com approval_id={self.approval_id}")
        if (self.published_release is not None) != (self.state == "published"):
            raise ValueError("published_release existe somente em rascunho publicado")
        base = self.base_release
        if base is not None and base.catalog_id != self.catalog.catalog_id:
            raise ValueError("base_release pertence a outro catálogo")
        return self


class DraftRevision(ContractModel):
    """Revisão imutável do conteúdo; editar cria a próxima, nunca altera esta."""

    draft_id: LocalId
    revision: PositiveInt
    parent_revision: PositiveInt | None = None
    content: CatalogContent
    content_sha256: Sha256Hex
    origin: RevisionOrigin
    reason: NonEmptyText
    operations: tuple[NonEmptyText, ...] = ()
    created_by: ActorSnapshot
    created_at: UtcTimestamp

    @model_validator(mode="after")
    def _hash_matches_content(self) -> Self:
        """O hash gravado identifica exatamente o conteúdo gravado."""
        if content_sha256(self.content) != self.content_sha256:
            raise ValueError("content_sha256 não corresponde ao conteúdo da revisão")
        if self.revision == 1:
            if self.parent_revision is not None:
                raise ValueError("a revisão 1 não tem revisão anterior")
        elif self.parent_revision != self.revision - 1:
            raise ValueError("revisão deriva sempre da imediatamente anterior")
        return self


class DraftHead(ContractModel):
    """Estado do rascunho e identidade da revisão atual (número e hash do conteúdo)."""

    draft: DraftRecord
    revision: PositiveInt
    content_sha256: Sha256Hex


class UpsertEntity(ContractModel):
    """Inclui ou substitui uma proposta; o estado cadastral precisa ser ``draft``."""

    op: Literal["upsert"]
    kind: EntityKind
    entity: dict[str, Any]


class RemoveProposal(ContractModel):
    """Retira uma proposta deste rascunho.

    Proposta nova sai do rascunho. Proposta sobre entidade herdada do release-base
    (alteração ou depreciação) é descartada, e volta a valer exatamente a versão
    publicada. Entidade publicada sem proposta não sai: só pode ser depreciada.
    """

    op: Literal["remove"]
    kind: EntityKind
    entity_id: NonEmptyText


class DeprecateEntity(ContractModel):
    """Propõe depreciar uma entidade aprovada do release-base, sem alterar seus dados."""

    op: Literal["deprecate"]
    kind: LifecycleKind
    entity_id: LocalId


class DuplicateEntity(ContractModel):
    """Cria proposta copiando outra entidade com novo ID; exige revisão de identidade.

    Duplicar um uso (binding) não duplica o conceito: a cópia aponta o mesmo conceito.
    """

    op: Literal["duplicate"]
    kind: LifecycleKind
    source_id: LocalId
    new_id: LocalId


PatchOperation = Annotated[
    UpsertEntity | RemoveProposal | DeprecateEntity | DuplicateEntity, Field(discriminator="op")
]


class DraftPatch(ContractModel):
    """Conjunto de operações aplicado de uma vez sobre a revisão esperada."""

    operations: tuple[PatchOperation, ...] = Field(min_length=1)
    reason: NonEmptyText


# --- Validação ---------------------------------------------------------------------------

Severity = Literal["error", "warning", "pending"]
"""``error`` bloqueia submissão, aprovação e publicação; ``pending`` é pendência visível."""


class ValidationFinding(ContractModel):
    """Problema ou pendência localizado por entidade e campo, para a tela de curadoria."""

    severity: Severity
    code: NonEmptyText
    entity_kind: str | None = None
    entity_id: str | None = None
    field: str | None = None
    message: NonEmptyText


class ValidationSummary(ContractModel):
    """Resumo de um relatório de validação gravado em aprovação, candidato e recibo."""

    report_sha256: Sha256Hex
    validator_version: NonEmptyText
    errors: CountInt
    warnings: CountInt
    pending: CountInt


class ValidationReport(ContractModel):
    """Validação automática de uma revisão exata; não é revisão humana nem aprovação."""

    draft_id: LocalId
    revision: PositiveInt
    content_sha256: Sha256Hex
    base_release: CatalogReleaseRef | None = None
    validator_version: NonEmptyText
    findings: tuple[ValidationFinding, ...] = ()

    @property
    def passed(self) -> bool:
        """Sem erro bloqueante (avisos e pendências não bloqueiam por si)."""
        return not any(finding.severity == "error" for finding in self.findings)

    def by_severity(self, severity: Severity) -> tuple[ValidationFinding, ...]:
        """Achados de uma severidade, na ordem do relatório."""
        return tuple(finding for finding in self.findings if finding.severity == severity)

    def summary(self) -> ValidationSummary:
        """Resumo com o hash do relatório inteiro."""
        digest = hashlib.sha256(canonical_json_bytes(self.model_dump(mode="json"))).hexdigest()
        return ValidationSummary(
            report_sha256=digest,
            validator_version=self.validator_version,
            errors=len(self.by_severity("error")),
            warnings=len(self.by_severity("warning")),
            pending=len(self.by_severity("pending")),
        )


class PendingItem(ContractModel):
    """Pendência explícita que acompanha aprovação, candidato e recibo."""

    kind: Literal["reconciliation_decision", "carrier_pending"]
    entity_id: NonEmptyText
    detail: NonEmptyText


# --- Revisão humana e aprovação ---------------------------------------------------------

ReviewVerdict = Literal["approve", "request_changes", "reject"]


class ReviewRecord(ContractModel):
    """Decisão humana sobre uma revisão exata; ``approve`` é a aprovação de conteúdo."""

    review_id: LocalId
    draft_id: LocalId
    revision: PositiveInt
    content_sha256: Sha256Hex
    verdict: ReviewVerdict
    justification: NonEmptyText
    validation: ValidationSummary
    pending_items: tuple[PendingItem, ...] = ()
    reviewer: ActorSnapshot
    reviewed_at: UtcTimestamp
    command_id: CommandId


# --- Candidato e publicação -------------------------------------------------------------

CandidateState = Literal["prepared", "publishing", "published", "invalidated"]
"""Publicação abandonada devolve o candidato a ``prepared``; edição o invalida."""


class DiffSummary(ContractModel):
    """Contagem de mudanças por tipo de entidade em relação ao release anterior."""

    added: tuple[str, ...] = ()
    changed: tuple[str, ...] = ()
    deprecated: tuple[str, ...] = ()


class ReleaseCandidate(ContractModel):
    """Candidato isolado, montado da revisão aprovada, gravado em área de preparo e reaberto.

    Sua identidade é a do release que ele seria (catálogo, versão e SHA-256 do
    manifesto); a publicação precisa informar exatamente esses valores.
    """

    candidate_id: LocalId
    draft_id: LocalId
    revision: PositiveInt
    content_sha256: Sha256Hex
    approval_id: LocalId
    release: CatalogReleaseRef
    previous_release: CatalogReleaseRef | None = None
    content_origin: ContentOrigin
    manifest_created_at: UtcTimestamp
    terms: tuple[ComponentTerms, ...] = Field(min_length=1)
    release_content_sha256: Sha256Hex
    validation: ValidationSummary
    pending_items: tuple[PendingItem, ...] = ()
    diff: DiffSummary
    state: CandidateState
    prepared_by: ActorSnapshot
    prepared_at: UtcTimestamp
    command_id: CommandId
    closing_reason: str | None = None


IntentState = Literal["recorded", "completed", "abandoned"]


class PublicationIntent(ContractModel):
    """Intenção durável de publicar um candidato exato, gravada antes de tocar no disco.

    Banco e sistema de arquivos não têm transação conjunta (plano M6 §7.2): a intenção
    permite reconciliar uma publicação interrompida sem inventar aprovação.
    """

    intent_id: LocalId
    candidate_id: LocalId
    release: CatalogReleaseRef
    command_id: CommandId
    publisher: ActorSnapshot
    justification: NonEmptyText
    acknowledged_pending: tuple[str, ...] = ()
    recorded_at: UtcTimestamp
    recorded_event_seqs: tuple[PositiveInt, ...] = ()
    state: IntentState
    closed_at: UtcTimestamp | None = None
    closing_reason: str | None = None


IDENTITY_STATEMENT = (
    "Identificação informada localmente, sem autenticação: o registro comprova que a "
    "instalação gravou a ação e seus bytes, não quem a executou."
)
ADOPTION_STATEMENT = (
    "Publicar não atualiza nenhum projeto: cada projeto mantém seu release fixado até uma "
    "atualização explícita, que gera nova análise."
)


class PublicationReceipt(ContractModel):
    """Recibo de release disponível; só existe depois da verificação dos bytes promovidos."""

    receipt_id: LocalId
    release: CatalogReleaseRef
    previous_release: CatalogReleaseRef | None = None
    candidate_id: LocalId
    intent_id: LocalId
    draft_id: LocalId
    revision: PositiveInt
    content_sha256: Sha256Hex
    release_content_sha256: Sha256Hex
    approval_id: LocalId
    approved_by: ActorSnapshot
    approval_justification: NonEmptyText
    published_by: ActorSnapshot
    publication_justification: NonEmptyText
    completed_by: ActorSnapshot
    acknowledged_pending: tuple[str, ...] = ()
    validation: ValidationSummary
    pending_items: tuple[PendingItem, ...] = ()
    content_origin: ContentOrigin
    published_at: UtcTimestamp
    command_id: CommandId
    identity_assurance: Literal["unverified_local"] = "unverified_local"
    identity_statement: NonEmptyText = IDENTITY_STATEMENT
    adoption: Literal["explicit_per_project"] = "explicit_per_project"
    adoption_statement: NonEmptyText = ADOPTION_STATEMENT
    store_operational: bool
    artifact_store_operational: bool

    @model_validator(mode="after")
    def _statements_are_fixed(self) -> Self:
        """As declarações de identidade e de adoção não podem ser trocadas no recibo."""
        if (self.identity_statement, self.adoption_statement) != (
            IDENTITY_STATEMENT,
            ADOPTION_STATEMENT,
        ):
            raise ValueError("as declarações de identidade e de adoção do recibo são fixas")
        return self


# --- Eventos, recibos de comando e idempotência -----------------------------------------

SubjectKind = Literal["request", "draft", "review", "candidate", "intent", "publication"]


class EventDetail(ContractModel):
    """Par nome/valor que acompanha um evento (IDs, hashes, versões)."""

    name: NonEmptyText
    value: str


class CurationEvent(ContractModel):
    """Evento de domínio gravado na mesma transação do efeito; nunca alterado."""

    seq: PositiveInt | None = None
    event_id: LocalId
    at_utc: UtcTimestamp
    operation: NonEmptyText
    command_id: CommandId
    actor: ActorSnapshot
    subject_kind: SubjectKind
    subject_id: NonEmptyText
    from_state: str | None = None
    to_state: str | None = None
    revision: PositiveInt | None = None
    reason: str | None = None
    details: tuple[EventDetail, ...] = ()


class CommitReceipt(ContractModel):
    """Confirmação de que o efeito, os eventos e o registro do comando foram gravados."""

    command_id: CommandId
    operation: NonEmptyText
    subject_kind: SubjectKind
    subject_id: NonEmptyText
    revision: PositiveInt | None = None
    event_seqs: tuple[PositiveInt, ...] = Field(min_length=1)
    committed_at: UtcTimestamp
    store_operational: bool


CommandState = Literal["in_progress", "completed", "abandoned"]
"""``in_progress`` e ``abandoned`` só ocorrem na publicação, que atravessa banco e disco."""


class CommandRecord(ContractModel):
    """Chave idempotente: mesma chave e mesmo conteúdo devolvem o mesmo resultado."""

    command_id: CommandId
    operation: NonEmptyText
    payload_sha256: Sha256Hex
    actor_context_id: NonEmptyText
    state: CommandState
    recorded_at: UtcTimestamp
    receipt: CommitReceipt | None = None
    result: dict[str, Any] | None = None
    intent_id: LocalId | None = None

    @model_validator(mode="after")
    def _completed_has_result(self) -> Self:
        """Comando concluído tem recibo e resultado; em andamento, ainda não."""
        done = self.receipt is not None and self.result is not None
        if done != (self.state == "completed"):
            raise ValueError(f"comando {self.state} incoerente com recibo/resultado")
        return self


Value = TypeVar("Value")


@dataclass(frozen=True)
class CommandOutcome(Generic[Value]):
    """Resultado de um comando: recibo, valor e se foi repetição de comando já gravado."""

    receipt: CommitReceipt
    value: Value
    replayed: bool
