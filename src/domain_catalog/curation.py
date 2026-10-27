"""Serviço de curadoria do catálogo (E2, M1-08; parte do M1-14).

Solicitação → rascunho → validação → revisão → aprovação, com trilha durável. Cada
comando passa pelo mesmo executor:

1. valida a entrada antes de abrir transação;
2. procura a chave idempotente **antes** de qualquer pré-condição mutável (release-base,
   estado do rascunho): repetição devolve o recibo gravado, e chave reutilizada para
   outro pedido é conflito (plano M6 §6.3);
3. resgata o contexto de ator pela referência e aplica as regras de ``actor.authorize``;
4. numa única transação da porta ``CurationStore``: confere a chave de novo, aplica o
   efeito, grava eventos e o registro do comando com o recibo.

Mesma chave com o mesmo conteúdo devolve o recibo gravado sem novo efeito, ainda que o
estado tenha mudado depois; mesma chave com outro conteúdo, operação ou ator é
conflito. Qualquer falha desfaz a transação inteira: não há sucesso parcial. O serviço
não publica (ver ``publication.py``), não altera IDS nem IFC e não adota release em
projeto algum.
"""

import hashlib
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from src.domain_catalog.actor import (
    ActorContextResolver,
    ActorSnapshot,
    authorize,
    snapshot_actor,
)
from src.domain_catalog.canonical import canonical_json_bytes
from src.domain_catalog.content import CatalogContent
from src.domain_catalog.contracts import CatalogReleaseRef, ContractModel
from src.domain_catalog.curation_errors import (
    ActorContextError,
    CommandValidationError,
    ContentHashMismatchError,
    IdempotencyConflictError,
    InvalidTransitionError,
    RevisionConflictError,
    ValidationGateError,
)
from src.domain_catalog.curation_models import (
    LIFECYCLE_KINDS,
    TERMINAL_DRAFT_STATES,
    ChangeRequest,
    CommandMeta,
    CommandOutcome,
    CommandRecord,
    CommitReceipt,
    CurationEvent,
    DiffSummary,
    DraftHead,
    DraftPatch,
    DraftRecord,
    DraftRevision,
    EventDetail,
    OriginRef,
    PositiveInt,
    ReleaseCandidate,
    RequestedField,
    RequestState,
    ReviewRecord,
    ReviewVerdict,
    RevisionOrigin,
    SubjectKind,
    ValidationReport,
)
from src.domain_catalog.curation_models import (
    content_sha256 as hash_content,
)
from src.domain_catalog.curation_validation import (
    PENDING_CARRIER_POLICY,
    apply_patch,
    content_diff,
    entity_key,
    index_content,
    pending_items,
    rebuild_content,
    validate_revision,
)
from src.domain_catalog.draft_store import (
    CurationStore,
    CurationTransaction,
    insert_model,
    read_model,
    replace_model,
    require_model,
    scan_models,
)
from src.domain_catalog.models import LocalId, NonEmptyText, Sha256Hex
from src.domain_catalog.operations import DEFAULT_OPERATION_REGISTRY, OperationRegistry
from src.domain_catalog.package import CatalogIdentity
from src.domain_catalog.reader import CatalogReader

Result = TypeVar("Result", bound=BaseModel)
Input = TypeVar("Input", bound=BaseModel)


def utc_now() -> str:
    """Instante UTC atual no formato dos registros (segundos, sufixo ``Z``)."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_local_id() -> str:
    """Novo ID local estável (UUID em URN)."""
    return f"urn:uuid:{uuid.uuid4()}"


def evolve(record: Result, **changes: object) -> Result:
    """Cópia do registro com as mudanças, validada de novo (``model_copy`` não revalida)."""
    return type(record).model_validate({**record.model_dump(), **changes})


def validated_input(model: type[Input], **data: object) -> Input:
    """Valida a entrada de um comando antes de qualquer gravação."""
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        raise CommandValidationError(f"comando inválido: {problems}") from exc


class PublishedReleases(Protocol):
    """Releases já publicados (fornecidos pelo serviço de publicação)."""

    def open_published(self, ref: CatalogReleaseRef) -> CatalogReader:
        """Reader do release publicado com essa referência exata."""
        ...

    def latest_published(self, catalog_id: str) -> CatalogReleaseRef | None:
        """Último release publicado do catálogo, ou ``None``."""
        ...


@dataclass(frozen=True)
class Subject:
    """Registro principal afetado por um comando, citado no recibo."""

    kind: SubjectKind
    id: str
    revision: int | None = None


class CommandScope:
    """Transação, ator e instante de um comando em execução."""

    def __init__(
        self,
        tx: CurationTransaction,
        actor: ActorSnapshot,
        now: str,
        command_id: str,
        operation: str,
        new_id: Callable[[], str],
    ) -> None:
        """Contexto criado pelo executor; eventos emitidos aqui entram no recibo."""
        self.tx = tx
        self.actor = actor
        self.now = now
        self.command_id = command_id
        self.operation = operation
        self._new_id = new_id
        self.event_seqs: list[int] = []

    def new_id(self) -> str:
        """Novo ID local para registros e eventos deste comando."""
        return self._new_id()

    def emit(
        self,
        subject_kind: SubjectKind,
        subject_id: str,
        *,
        from_state: str | None,
        to_state: str | None,
        revision: int | None = None,
        reason: str | None = None,
        details: Mapping[str, str] | None = None,
    ) -> int:
        """Grava um evento de domínio na transação do comando e devolve a sequência."""
        event = CurationEvent(
            event_id=self.new_id(),
            at_utc=self.now,
            operation=self.operation,
            command_id=self.command_id,
            actor=self.actor,
            subject_kind=subject_kind,
            subject_id=subject_id,
            from_state=from_state,
            to_state=to_state,
            revision=revision,
            reason=reason,
            details=tuple(
                EventDetail(name=name, value=value) for name, value in (details or {}).items()
            ),
        )
        seq = self.tx.append_event(event.model_dump(mode="json", exclude={"seq"}))
        self.event_seqs.append(seq)
        return seq


def payload_sha256(operation: str, actor_context_id: str, payload: Mapping[str, Any]) -> str:
    """Hash canônico do comando para a comparação idempotente."""
    document = {"actor_context_id": actor_context_id, "operation": operation, "payload": payload}
    return hashlib.sha256(canonical_json_bytes(document)).hexdigest()


class CommandRunner:
    """Executa comandos com ator resgatado, idempotência e efeito, evento e recibo atômicos."""

    def __init__(
        self,
        store: CurationStore,
        actors: ActorContextResolver,
        clock: Callable[[], str],
        new_id: Callable[[], str],
    ) -> None:
        """Portas de persistência e de ator, relógio UTC e gerador de IDs."""
        self.store = store
        self._actors = actors
        self.clock = clock
        self.new_id = new_id

    def resolve_actor(self, actor_context_id: str) -> ActorSnapshot:
        """Contexto resgatado no backend e validado; desconhecido é ``ActorContextError``."""
        context = self._actors.resolve(actor_context_id)
        if context is None:
            raise ActorContextError(f"contexto de ator desconhecido: {actor_context_id}")
        return snapshot_actor(context)

    def authorized_actor(self, meta: CommandMeta, operation: str) -> ActorSnapshot:
        """Ator do comando, já conferido contra as regras da operação."""
        actor = self.resolve_actor(meta.actor_context_id)
        authorize(operation, actor)
        return actor

    @staticmethod
    def replay(
        tx: CurationTransaction,
        meta: CommandMeta,
        operation: str,
        digest: str,
        result_model: type[Result],
    ) -> CommandOutcome[Result] | None:
        """Recibo gravado para a mesma chave e conteúdo, ou ``None`` se a chave é nova."""
        found = read_model(tx, "command", meta.command_id, CommandRecord)
        if found is None:
            return None
        record, _ = found
        if (record.operation, record.payload_sha256, record.actor_context_id) != (
            operation,
            digest,
            meta.actor_context_id,
        ):
            raise IdempotencyConflictError(
                f"chave {meta.command_id} já usada por outro comando ({record.operation}); "
                "use uma chave nova para um pedido diferente"
            )
        if record.state == "abandoned":
            raise InvalidTransitionError(
                f"comando {meta.command_id} foi abandonado; envie um pedido novo com outra chave"
            )
        if record.receipt is None or record.result is None:
            raise InvalidTransitionError(
                f"comando {meta.command_id} ainda está em andamento; consulte-o ou retome-o"
            )
        return CommandOutcome(
            receipt=record.receipt,
            value=result_model.model_validate(record.result),
            replayed=True,
        )

    def lookup(
        self,
        meta: CommandMeta,
        operation: str,
        payload: Mapping[str, Any],
        result_model: type[Result],
    ) -> CommandOutcome[Result] | None:
        """Consulta prévia da chave, antes de pré-condições mutáveis e de trabalho fora do banco.

        Repetição exata devolve o recibo gravado, qualquer que seja o estado atual (base
        superada, release novo, reinício); chave usada por outro pedido é conflito.
        """
        digest = payload_sha256(operation, meta.actor_context_id, payload)
        with self.store.transaction() as tx:
            return self.replay(tx, meta, operation, digest, result_model)

    def execute(
        self,
        meta: CommandMeta,
        operation: str,
        payload: Mapping[str, Any],
        result_model: type[Result],
        body: Callable[[CommandScope], tuple[Result, Subject]],
    ) -> CommandOutcome[Result]:
        """Roda ``body`` numa transação; repetição devolve o recibo, falha não grava nada."""
        actor = self.authorized_actor(meta, operation)
        digest = payload_sha256(operation, meta.actor_context_id, payload)
        with self.store.transaction() as tx:
            replayed = self.replay(tx, meta, operation, digest, result_model)
            if replayed is not None:
                return replayed
            scope = CommandScope(tx, actor, self.clock(), meta.command_id, operation, self.new_id)
            value, subject = body(scope)
            receipt = self.complete(scope, digest, subject, value)
        return CommandOutcome(receipt=receipt, value=value, replayed=False)

    def complete(
        self, scope: CommandScope, digest: str, subject: Subject, value: BaseModel
    ) -> CommitReceipt:
        """Grava o registro do comando concluído com seu recibo, na transação aberta."""
        receipt = CommitReceipt(
            command_id=scope.command_id,
            operation=scope.operation,
            subject_kind=subject.kind,
            subject_id=subject.id,
            revision=subject.revision,
            event_seqs=tuple(scope.event_seqs),
            committed_at=scope.now,
            store_operational=self.store.operational,
        )
        record = CommandRecord(
            command_id=scope.command_id,
            operation=scope.operation,
            payload_sha256=digest,
            actor_context_id=scope.actor.actor_context_id,
            state="completed",
            recorded_at=scope.now,
            receipt=receipt,
            result=value.model_dump(mode="json"),
        )
        found = read_model(scope.tx, "command", scope.command_id, CommandRecord)
        if found is None:
            insert_model(scope.tx, "command", scope.command_id, record)
        else:
            replace_model(scope.tx, "command", scope.command_id, found[1], record)
        return receipt


# --- Entradas de comandos ----------------------------------------------------------------


class _RequestChangeInput(ContractModel):
    catalog_id: LocalId
    motivation: NonEmptyText
    field: RequestedField
    origin_refs: tuple[OriginRef, ...] = ()


class _RequestActionInput(ContractModel):
    request_id: LocalId
    reason: NonEmptyText


class _CreateDraftInput(ContractModel):
    title: NonEmptyText
    catalog: CatalogIdentity | None = None
    base_release: CatalogReleaseRef | None = None
    request_ids: tuple[LocalId, ...] = ()
    reason: NonEmptyText


class _ImportDraftInput(ContractModel):
    title: NonEmptyText
    catalog: CatalogIdentity
    content: CatalogContent
    source_label: NonEmptyText
    base_release: CatalogReleaseRef | None = None
    request_ids: tuple[LocalId, ...] = ()
    reason: NonEmptyText


class _EditDraftInput(ContractModel):
    draft_id: LocalId
    expected_revision: PositiveInt
    patch: DraftPatch


class _DraftActionInput(ContractModel):
    draft_id: LocalId
    reason: NonEmptyText


class _ExactRevisionInput(ContractModel):
    draft_id: LocalId
    revision: PositiveInt
    content_sha256: Sha256Hex
    reason: NonEmptyText


class _ReviewInput(ContractModel):
    draft_id: LocalId
    revision: PositiveInt
    content_sha256: Sha256Hex
    verdict: ReviewVerdict
    justification: NonEmptyText


_EDITABLE_DRAFT_STATES: frozenset[str] = frozenset({"editing", "in_review", "approved"})
"""Estados em que editar é permitido; editar volta a ``editing`` e invalida aprovação."""

_REQUEST_RETURN_STATES: frozenset[str] = frozenset({"in_review", "approved"})


def revision_key(draft_id: str, revision: int) -> str:
    """Chave da revisão no armazenamento (ordem de chave = ordem de revisão)."""
    return f"{draft_id}#{revision:06d}"


_REQUEST_TRANSITIONS: dict[tuple[str, str], RequestState] = {
    ("open", "triage"): "in_triage",
    ("open", "reject"): "rejected",
    ("in_triage", "reject"): "rejected",
    ("in_review", "reject"): "rejected",
    ("open", "cancel"): "cancelled",
    ("in_triage", "cancel"): "cancelled",
    ("in_review", "cancel"): "cancelled",
    ("open", "link"): "in_triage",
    ("in_triage", "link"): "in_triage",
    ("in_triage", "submit"): "in_review",
    ("in_review", "approve"): "approved",
    ("in_review", "return"): "in_triage",
    ("approved", "return"): "in_triage",
}
"""Transições da solicitação: comandos explícitos e efeitos do rascunho que a atende."""


def next_request_state(current: str, action: str) -> RequestState:
    """Estado seguinte da solicitação; transição fora da tabela é recusada."""
    try:
        return _REQUEST_TRANSITIONS[(current, action)]
    except KeyError:
        raise InvalidTransitionError(
            f"solicitação em {current} não admite a ação {action}"
        ) from None


class CurationService:
    """Curadoria do catálogo sobre as portas de ator e de persistência (M6).

    Sem adaptadores operacionais do M6, só roda com os adaptadores de teste, que se
    declaram não operacionais nos recibos.
    """

    def __init__(
        self,
        store: CurationStore,
        actors: ActorContextResolver,
        *,
        releases: PublishedReleases | None = None,
        registry: OperationRegistry = DEFAULT_OPERATION_REGISTRY,
        clock: Callable[[], str] = utc_now,
        new_id: Callable[[], str] = new_local_id,
    ) -> None:
        """Portas de persistência e de ator; ``releases`` dá acesso a releases publicados."""
        self._runner = CommandRunner(store, actors, clock, new_id)
        self._store = store
        self._releases = releases
        self._registry = registry

    # --- consultas --------------------------------------------------------------------

    def get_request(self, request_id: str) -> ChangeRequest:
        """Solicitação pelo ID."""
        with self._store.transaction() as tx:
            return require_model(tx, "request", request_id, ChangeRequest, "solicitação")[0]

    def list_requests(
        self, *, catalog_id: str | None = None, state: str | None = None
    ) -> tuple[ChangeRequest, ...]:
        """Solicitações filtradas, em ordem de registro."""
        with self._store.transaction() as tx:
            found = [request for request, _ in scan_models(tx, "request", ChangeRequest)]
        return tuple(
            request
            for request in sorted(found, key=lambda r: (r.requested_at, r.request_id))
            if (catalog_id is None or request.catalog_id == catalog_id)
            and (state is None or request.state == state)
        )

    def events(self, after_seq: int = 0) -> tuple[CurationEvent, ...]:
        """Eventos confirmados depois da sequência dada, em ordem."""
        with self._store.transaction() as tx:
            rows = tx.events(after_seq)
        return tuple(
            CurationEvent.model_validate({**document, "seq": seq}) for seq, document in rows
        )

    def get_command(self, command_id: str) -> CommandRecord | None:
        """Registro de um comando pela chave, para resolver resposta perdida."""
        with self._store.transaction() as tx:
            found = read_model(tx, "command", command_id, CommandRecord)
        return None if found is None else found[0]

    # --- solicitações -----------------------------------------------------------------

    def request_change(
        self,
        command: CommandMeta,
        *,
        catalog_id: str,
        motivation: str,
        field: RequestedField,
        origin_refs: Sequence[OriginRef] = (),
    ) -> CommandOutcome[ChangeRequest]:
        """Registra uma solicitação aberta; não cria equivalência nem altera release."""
        data = validated_input(
            _RequestChangeInput,
            catalog_id=catalog_id,
            motivation=motivation,
            field=field,
            origin_refs=tuple(origin_refs),
        )

        def body(scope: CommandScope) -> tuple[ChangeRequest, Subject]:
            request = ChangeRequest(
                request_id=scope.new_id(),
                catalog_id=data.catalog_id,
                state="open",
                motivation=data.motivation,
                field=data.field,
                origin_refs=data.origin_refs,
                requested_by=scope.actor,
                requested_at=scope.now,
            )
            insert_model(scope.tx, "request", request.request_id, request)
            scope.emit(
                "request",
                request.request_id,
                from_state=None,
                to_state="open",
                details={"catalog_id": data.catalog_id, "field_name": data.field.field_name},
            )
            return request, Subject("request", request.request_id)

        return self._runner.execute(
            command, "request_change", data.model_dump(mode="json"), ChangeRequest, body
        )

    def triage_request(
        self, command: CommandMeta, *, request_id: str, reason: str
    ) -> CommandOutcome[ChangeRequest]:
        """Curadoria assume a solicitação aberta."""
        return self._act_on_request(command, "triage_request", "triage", request_id, reason)

    def reject_request(
        self, command: CommandMeta, *, request_id: str, justification: str
    ) -> CommandOutcome[ChangeRequest]:
        """Rejeição com justificativa e responsável declarado; estado terminal."""
        return self._act_on_request(command, "reject_request", "reject", request_id, justification)

    def cancel_request(
        self, command: CommandMeta, *, request_id: str, reason: str
    ) -> CommandOutcome[ChangeRequest]:
        """Cancelamento com motivo; estado terminal."""
        return self._act_on_request(command, "cancel_request", "cancel", request_id, reason)

    def _act_on_request(
        self, command: CommandMeta, operation: str, action: str, request_id: str, reason: str
    ) -> CommandOutcome[ChangeRequest]:
        data = validated_input(_RequestActionInput, request_id=request_id, reason=reason)

        def body(scope: CommandScope) -> tuple[ChangeRequest, Subject]:
            request, version = require_model(
                scope.tx, "request", data.request_id, ChangeRequest, "solicitação"
            )
            target = next_request_state(request.state, action)
            closing = data.reason if action in ("reject", "cancel") else request.closing_reason
            updated = evolve(request, state=target, closing_reason=closing)
            replace_model(scope.tx, "request", request.request_id, version, updated)
            scope.emit(
                "request",
                request.request_id,
                from_state=request.state,
                to_state=target,
                reason=data.reason,
            )
            return updated, Subject("request", request.request_id)

        return self._runner.execute(
            command, operation, data.model_dump(mode="json"), ChangeRequest, body
        )

    # --- rascunhos: consultas -----------------------------------------------------------

    def get_draft(self, draft_id: str) -> DraftRecord:
        """Rascunho pelo ID."""
        with self._store.transaction() as tx:
            return require_model(tx, "draft", draft_id, DraftRecord, "rascunho")[0]

    def get_head(self, draft_id: str) -> DraftHead:
        """Estado do rascunho com o número e o hash da revisão atual."""
        with self._store.transaction() as tx:
            draft = require_model(tx, "draft", draft_id, DraftRecord, "rascunho")[0]
            revision = self._revision(tx, draft_id, draft.current_revision)
        return DraftHead(
            draft=draft, revision=revision.revision, content_sha256=revision.content_sha256
        )

    def get_revision(self, draft_id: str, revision: int) -> DraftRevision:
        """Revisão imutável de um rascunho; revisões antigas continuam consultáveis."""
        with self._store.transaction() as tx:
            return self._revision(tx, draft_id, revision)

    def list_revisions(self, draft_id: str) -> tuple[DraftRevision, ...]:
        """Todas as revisões do rascunho, da primeira à atual."""
        with self._store.transaction() as tx:
            draft = require_model(tx, "draft", draft_id, DraftRecord, "rascunho")[0]
            return tuple(
                self._revision(tx, draft_id, number)
                for number in range(1, draft.current_revision + 1)
            )

    def list_drafts(
        self, *, catalog_id: str | None = None, state: str | None = None
    ) -> tuple[DraftRecord, ...]:
        """Rascunhos filtrados por catálogo e estado, em ordem de criação."""
        with self._store.transaction() as tx:
            found = [draft for draft, _ in scan_models(tx, "draft", DraftRecord)]
        return tuple(
            draft
            for draft in sorted(found, key=lambda d: (d.created_at, d.draft_id))
            if (catalog_id is None or draft.catalog.catalog_id == catalog_id)
            and (state is None or draft.state == state)
        )

    def list_reviews(self, draft_id: str) -> tuple[ReviewRecord, ...]:
        """Revisões humanas registradas para o rascunho, inclusive as já invalidadas."""
        with self._store.transaction() as tx:
            reviews = [review for review, _ in scan_models(tx, "review", ReviewRecord)]
        return tuple(
            review
            for review in sorted(reviews, key=lambda r: (r.reviewed_at, r.review_id))
            if review.draft_id == draft_id
        )

    def validate_draft(self, draft_id: str, revision: int | None = None) -> ValidationReport:
        """Validação automática de uma revisão exata (a atual, se não informada)."""
        draft = self.get_draft(draft_id)
        number = draft.current_revision if revision is None else revision
        content = self.get_revision(draft_id, number).content
        return self._validate(draft, number, content, self._base_content(draft))

    def diff_revision(self, draft_id: str, revision: int | None = None) -> DiffSummary:
        """Mudanças da revisão em relação ao release-base, para revisão lado a lado."""
        draft = self.get_draft(draft_id)
        number = draft.current_revision if revision is None else revision
        return content_diff(self._base_content(draft), self.get_revision(draft_id, number).content)

    # --- rascunhos: comandos ------------------------------------------------------------

    def create_draft(
        self,
        command: CommandMeta,
        *,
        title: str,
        reason: str,
        catalog: CatalogIdentity | None = None,
        base_release: CatalogReleaseRef | None = None,
        request_ids: Sequence[str] = (),
    ) -> CommandOutcome[DraftHead]:
        """Abre rascunho vazio (primeiro release) ou a partir do último release publicado."""
        data = validated_input(
            _CreateDraftInput,
            title=title,
            catalog=catalog,
            base_release=base_release,
            request_ids=tuple(dict.fromkeys(request_ids)),
            reason=reason,
        )
        payload = data.model_dump(mode="json")
        replayed = self._runner.lookup(command, "create_draft", payload, DraftHead)
        if replayed is not None:
            return replayed
        try:
            identity, base_content = self._resolve_base(data.catalog, data.base_release)
        except CommandValidationError:
            # Uma chamada idêntica pode ter concluído após o lookup inicial.
            replayed = self._runner.lookup(command, "create_draft", payload, DraftHead)
            if replayed is not None:
                return replayed
            raise
        origin: RevisionOrigin = "empty" if base_content is None else "base_release"
        initial = base_content if base_content is not None else CatalogContent()
        return self._open_draft(
            command,
            "create_draft",
            payload,
            identity,
            data.base_release,
            data.title,
            initial,
            origin,
            (),
            data.reason,
            data.request_ids,
        )

    def import_draft(
        self,
        command: CommandMeta,
        *,
        title: str,
        catalog: CatalogIdentity,
        content: CatalogContent,
        source_label: str,
        reason: str,
        base_release: CatalogReleaseRef | None = None,
        request_ids: Sequence[str] = (),
    ) -> CommandOutcome[DraftHead]:
        """Importa propostas de uma fonte como rascunho; nunca aprova nem publica.

        Toda entidade importada com estado cadastral precisa estar em ``draft``. Sobre
        um release-base, a importação só acrescenta: entidade publicada não é alterada.
        """
        data = validated_input(
            _ImportDraftInput,
            title=title,
            catalog=catalog,
            content=content,
            source_label=source_label,
            base_release=base_release,
            request_ids=tuple(dict.fromkeys(request_ids)),
            reason=reason,
        )
        not_draft = [
            f"{kind} {getattr(entity, 'id', '?')} em {state}"
            for kind, entity in data.content.iter_entities()
            if kind in LIFECYCLE_KINDS and (state := getattr(entity, "lifecycle", None)) != "draft"
        ]
        if not_draft:
            raise CommandValidationError(
                "importação só cria propostas em draft; recebido: " + "; ".join(not_draft)
            )
        payload = data.model_dump(mode="json")
        replayed = self._runner.lookup(command, "import_draft", payload, DraftHead)
        if replayed is not None:
            return replayed
        try:
            identity, base_content = self._resolve_base(data.catalog, data.base_release)
        except CommandValidationError:
            # Não transformar recibo concorrente em recusa por mudança da base.
            replayed = self._runner.lookup(command, "import_draft", payload, DraftHead)
            if replayed is not None:
                return replayed
            raise
        merged = _merge_import(base_content, data.content)
        return self._open_draft(
            command,
            "import_draft",
            payload,
            identity,
            data.base_release,
            data.title,
            merged,
            "import",
            (f"import {data.source_label}",),
            data.reason,
            data.request_ids,
        )

    def edit_draft(
        self, command: CommandMeta, *, draft_id: str, expected_revision: int, patch: DraftPatch
    ) -> CommandOutcome[DraftHead]:
        """Aplica o patch sobre a revisão esperada e cria a próxima revisão.

        Revisão esperada diferente da atual é conflito, sem sobrescrita. Editar um
        rascunho em revisão ou aprovado volta-o a ``editing`` e invalida a aprovação.
        """
        data = validated_input(
            _EditDraftInput, draft_id=draft_id, expected_revision=expected_revision, patch=patch
        )
        payload = data.model_dump(mode="json")
        replayed = self._runner.lookup(command, "edit_draft", payload, DraftHead)
        if replayed is not None:
            return replayed
        base_content = self._base_content_of(data.draft_id)

        def body(scope: CommandScope) -> tuple[DraftHead, Subject]:
            draft, version = require_model(
                scope.tx, "draft", data.draft_id, DraftRecord, "rascunho"
            )
            if draft.state not in _EDITABLE_DRAFT_STATES:
                raise InvalidTransitionError(f"rascunho em {draft.state} não admite edição")
            if data.expected_revision != draft.current_revision:
                raise RevisionConflictError(
                    f"rascunho está na revisão {draft.current_revision}, não na "
                    f"{data.expected_revision}; concilie as mudanças antes de editar",
                    expected=data.expected_revision,
                    current=draft.current_revision,
                )
            current = self._revision(scope.tx, draft.draft_id, draft.current_revision)
            content, log = apply_patch(current.content, data.patch, base=base_content)
            number = draft.current_revision + 1
            origin: RevisionOrigin = (
                "assistant_proposal" if scope.actor.actor_kind == "assistant" else "human_edit"
            )
            revision = DraftRevision(
                draft_id=draft.draft_id,
                revision=number,
                parent_revision=draft.current_revision,
                content=content,
                content_sha256=hash_content(content),
                origin=origin,
                reason=data.patch.reason,
                operations=log,
                created_by=scope.actor,
                created_at=scope.now,
            )
            insert_model(scope.tx, "revision", revision_key(draft.draft_id, number), revision)
            self._withdraw(scope, draft, f"revisão {number} criada: aprovação anterior não vale")
            updated = evolve(
                draft,
                state="editing",
                current_revision=number,
                approval_id=None,
                candidate_id=None,
                updated_at=scope.now,
            )
            replace_model(scope.tx, "draft", draft.draft_id, version, updated)
            scope.emit(
                "draft",
                draft.draft_id,
                from_state=draft.state,
                to_state="editing",
                revision=number,
                reason=data.patch.reason,
                details={"content_sha256": revision.content_sha256, "origin": origin},
            )
            head = DraftHead(draft=updated, revision=number, content_sha256=revision.content_sha256)
            return head, Subject("draft", draft.draft_id, number)

        return self._runner.execute(command, "edit_draft", payload, DraftHead, body)

    def cancel_draft(
        self, command: CommandMeta, *, draft_id: str, reason: str
    ) -> CommandOutcome[DraftHead]:
        """Encerra o rascunho sem publicar; revisões e eventos continuam no histórico."""
        data = validated_input(_DraftActionInput, draft_id=draft_id, reason=reason)

        def body(scope: CommandScope) -> tuple[DraftHead, Subject]:
            draft, version = require_model(
                scope.tx, "draft", data.draft_id, DraftRecord, "rascunho"
            )
            if draft.state not in _EDITABLE_DRAFT_STATES:
                raise InvalidTransitionError(f"rascunho em {draft.state} não pode ser cancelado")
            self._withdraw(scope, draft, f"rascunho cancelado: {data.reason}")
            updated = evolve(
                draft,
                state="cancelled",
                approval_id=None,
                candidate_id=None,
                closing_reason=data.reason,
                updated_at=scope.now,
            )
            replace_model(scope.tx, "draft", draft.draft_id, version, updated)
            scope.emit(
                "draft",
                draft.draft_id,
                from_state=draft.state,
                to_state="cancelled",
                revision=draft.current_revision,
                reason=data.reason,
            )
            return self._head(scope.tx, updated), Subject(
                "draft", draft.draft_id, draft.current_revision
            )

        return self._runner.execute(
            command, "cancel_draft", data.model_dump(mode="json"), DraftHead, body
        )

    # --- revisão humana -----------------------------------------------------------------

    def submit_for_review(
        self,
        command: CommandMeta,
        *,
        draft_id: str,
        revision: int,
        content_sha256: str,
        reason: str,
    ) -> CommandOutcome[DraftHead]:
        """Leva a revisão exata à revisão humana; exige validação automática sem erro."""
        data = validated_input(
            _ExactRevisionInput,
            draft_id=draft_id,
            revision=revision,
            content_sha256=content_sha256,
            reason=reason,
        )
        payload = data.model_dump(mode="json")
        replayed = self._runner.lookup(command, "submit_for_review", payload, DraftHead)
        if replayed is not None:
            return replayed
        base_content = self._base_content_of(data.draft_id)

        def body(scope: CommandScope) -> tuple[DraftHead, Subject]:
            draft, version = require_model(
                scope.tx, "draft", data.draft_id, DraftRecord, "rascunho"
            )
            if draft.state != "editing":
                raise InvalidTransitionError(f"rascunho em {draft.state} não pode ser submetido")
            current = self._exact_revision(scope.tx, draft, data.revision, data.content_sha256)
            report = self._passing_report(draft, current, base_content, "submissão")
            updated = evolve(draft, state="in_review", updated_at=scope.now)
            replace_model(scope.tx, "draft", draft.draft_id, version, updated)
            summary = report.summary()
            scope.emit(
                "draft",
                draft.draft_id,
                from_state="editing",
                to_state="in_review",
                revision=data.revision,
                reason=data.reason,
                details={
                    "content_sha256": data.content_sha256,
                    "validation_report_sha256": summary.report_sha256,
                },
            )
            self._move_requests(scope, draft.draft_id, "submit")
            head = DraftHead(
                draft=updated, revision=data.revision, content_sha256=data.content_sha256
            )
            return head, Subject("draft", draft.draft_id, data.revision)

        return self._runner.execute(command, "submit_for_review", payload, DraftHead, body)

    def review_draft(
        self,
        command: CommandMeta,
        *,
        draft_id: str,
        revision: int,
        content_sha256: str,
        verdict: ReviewVerdict,
        justification: str,
    ) -> CommandOutcome[ReviewRecord]:
        """Decisão humana sobre a revisão exata em revisão: aprovar, pedir mudança ou rejeitar.

        ``approve`` é a aprovação de conteúdo: liga-se ao número e ao hash da revisão,
        exige validação sem erro, responsável declarado e justificativa, e deixa de valer
        com qualquer edição posterior. Aprovar não publica.
        """
        data = validated_input(
            _ReviewInput,
            draft_id=draft_id,
            revision=revision,
            content_sha256=content_sha256,
            verdict=verdict,
            justification=justification,
        )
        payload = data.model_dump(mode="json")
        replayed = self._runner.lookup(command, "review_draft", payload, ReviewRecord)
        if replayed is not None:
            return replayed
        base_content = self._base_content_of(data.draft_id)

        def body(scope: CommandScope) -> tuple[ReviewRecord, Subject]:
            draft, version = require_model(
                scope.tx, "draft", data.draft_id, DraftRecord, "rascunho"
            )
            if draft.state != "in_review":
                raise InvalidTransitionError(
                    f"rascunho em {draft.state} não está em revisão; submeta a revisão atual"
                )
            current = self._exact_revision(scope.tx, draft, data.revision, data.content_sha256)
            if data.verdict == "approve":
                report = self._passing_report(draft, current, base_content, "aprovação")
            else:
                report = self._validate(draft, current.revision, current.content, base_content)
            review = ReviewRecord(
                review_id=scope.new_id(),
                draft_id=draft.draft_id,
                revision=current.revision,
                content_sha256=current.content_sha256,
                verdict=data.verdict,
                justification=data.justification,
                validation=report.summary(),
                pending_items=pending_items(current.content),
                reviewer=scope.actor,
                reviewed_at=scope.now,
                command_id=scope.command_id,
            )
            insert_model(scope.tx, "review", review.review_id, review)
            target, request_action, approval, closing = {
                "approve": ("approved", "approve", review.review_id, None),
                "request_changes": ("editing", "return", None, None),
                "reject": ("rejected", "return", None, data.justification),
            }[data.verdict]
            updated = evolve(
                draft,
                state=target,
                approval_id=approval,
                closing_reason=closing,
                updated_at=scope.now,
            )
            replace_model(scope.tx, "draft", draft.draft_id, version, updated)
            scope.emit(
                "review",
                review.review_id,
                from_state=None,
                to_state=data.verdict,
                revision=current.revision,
                reason=data.justification,
                details={
                    "draft_id": draft.draft_id,
                    "content_sha256": current.content_sha256,
                    "validation_report_sha256": review.validation.report_sha256,
                },
            )
            scope.emit(
                "draft",
                draft.draft_id,
                from_state="in_review",
                to_state=target,
                revision=current.revision,
                reason=data.justification,
            )
            self._move_requests(scope, draft.draft_id, request_action)
            return review, Subject("review", review.review_id, current.revision)

        return self._runner.execute(command, "review_draft", payload, ReviewRecord, body)

    def _exact_revision(
        self, tx: CurationTransaction, draft: DraftRecord, revision: int, digest: str
    ) -> DraftRevision:
        """A revisão atual, conferida pelo número e pelo hash informados."""
        if revision != draft.current_revision:
            raise RevisionConflictError(
                f"a revisão atual é {draft.current_revision}, não {revision}",
                expected=revision,
                current=draft.current_revision,
            )
        current = self._revision(tx, draft.draft_id, revision)
        if current.content_sha256 != digest:
            raise ContentHashMismatchError(
                f"hash informado não é o do conteúdo da revisão {revision} "
                f"({current.content_sha256})"
            )
        return current

    def _passing_report(
        self,
        draft: DraftRecord,
        revision: DraftRevision,
        base: CatalogContent | None,
        action: str,
    ) -> ValidationReport:
        """Relatório da revisão; erro bloqueante impede a ação, com os códigos na mensagem."""
        report = self._validate(draft, revision.revision, revision.content, base)
        if not report.passed:
            errors = report.by_severity("error")
            codes = ", ".join(sorted({finding.code for finding in errors}))
            raise ValidationGateError(
                f"{action} recusada: {len(errors)} erro(s) de validação na revisão "
                f"{revision.revision} ({codes}); consulte validate_draft"
            )
        return report

    # --- rascunhos: apoio ---------------------------------------------------------------

    @staticmethod
    def _revision(tx: CurationTransaction, draft_id: str, revision: int) -> DraftRevision:
        return require_model(
            tx, "revision", revision_key(draft_id, revision), DraftRevision, "revisão"
        )[0]

    def _head(self, tx: CurationTransaction, draft: DraftRecord) -> DraftHead:
        revision = self._revision(tx, draft.draft_id, draft.current_revision)
        return DraftHead(
            draft=draft, revision=revision.revision, content_sha256=revision.content_sha256
        )

    def _validate(
        self,
        draft: DraftRecord,
        revision: int,
        content: CatalogContent,
        base: CatalogContent | None,
    ) -> ValidationReport:
        return validate_revision(
            draft_id=draft.draft_id,
            revision=revision,
            content=content,
            base=base,
            base_release=draft.base_release,
            registry=self._registry,
            pending_carrier_policy=PENDING_CARRIER_POLICY,
        )

    def _published(self) -> PublishedReleases:
        if self._releases is None:
            raise CommandValidationError(
                "serviço sem acesso a releases publicados: não é possível usar release-base"
            )
        return self._releases

    def _base_content(self, draft: DraftRecord) -> CatalogContent | None:
        """Conteúdo do release-base, lido fora de qualquer transação de comando."""
        if draft.base_release is None:
            return None
        return self._published().open_published(draft.base_release).content

    def _base_content_of(self, draft_id: str) -> CatalogContent | None:
        with self._store.transaction() as tx:
            found = read_model(tx, "draft", draft_id, DraftRecord)
        return None if found is None else self._base_content(found[0])

    def _resolve_base(
        self, catalog: CatalogIdentity | None, base_release: CatalogReleaseRef | None
    ) -> tuple[CatalogIdentity, CatalogContent | None]:
        """Identidade do catálogo e conteúdo-base; o base precisa ser o último publicado."""
        if base_release is None:
            if catalog is None:
                raise CommandValidationError(
                    "rascunho sem release-base exige a identidade do catálogo"
                )
            latest = (
                None
                if self._releases is None
                else self._releases.latest_published(catalog.catalog_id)
            )
            if latest is not None:
                raise CommandValidationError(
                    f"catálogo já tem release publicado ({latest.version}); abra o rascunho a "
                    "partir dele para não descartar o histórico"
                )
            return catalog, None
        releases = self._published()
        latest = releases.latest_published(base_release.catalog_id)
        if latest != base_release:
            raise CommandValidationError(
                f"release-base {base_release.version} não é o último publicado do catálogo "
                f"({None if latest is None else latest.version})"
            )
        reader = releases.open_published(base_release)
        identity = reader.describe().catalog
        if catalog is not None and catalog != identity:
            raise CommandValidationError("identidade informada difere da do release-base")
        return identity, reader.content

    def _open_draft(
        self,
        command: CommandMeta,
        operation: str,
        payload: Mapping[str, Any],
        identity: CatalogIdentity,
        base_release: CatalogReleaseRef | None,
        title: str,
        content: CatalogContent,
        origin: RevisionOrigin,
        operations: tuple[str, ...],
        reason: str,
        request_ids: tuple[str, ...],
    ) -> CommandOutcome[DraftHead]:
        def body(scope: CommandScope) -> tuple[DraftHead, Subject]:
            draft_id = scope.new_id()
            revision = DraftRevision(
                draft_id=draft_id,
                revision=1,
                content=content,
                content_sha256=hash_content(content),
                origin=origin,
                reason=reason,
                operations=operations,
                created_by=scope.actor,
                created_at=scope.now,
            )
            draft = DraftRecord(
                draft_id=draft_id,
                catalog=identity,
                title=title,
                state="editing",
                current_revision=1,
                base_release=base_release,
                created_by=scope.actor,
                created_at=scope.now,
                updated_at=scope.now,
            )
            insert_model(scope.tx, "draft", draft_id, draft)
            insert_model(scope.tx, "revision", revision_key(draft_id, 1), revision)
            scope.emit(
                "draft",
                draft_id,
                from_state=None,
                to_state="editing",
                revision=1,
                reason=reason,
                details={"content_sha256": revision.content_sha256, "origin": origin},
            )
            self._link_requests(scope, request_ids, identity.catalog_id, draft_id)
            head = DraftHead(draft=draft, revision=1, content_sha256=revision.content_sha256)
            return head, Subject("draft", draft_id, 1)

        return self._runner.execute(command, operation, payload, DraftHead, body)

    def _link_requests(
        self, scope: CommandScope, request_ids: tuple[str, ...], catalog_id: str, draft_id: str
    ) -> None:
        """Vincula solicitações do mesmo catálogo ainda sem rascunho ativo."""
        for request_id in request_ids:
            request, version = require_model(
                scope.tx, "request", request_id, ChangeRequest, "solicitação"
            )
            if request.catalog_id != catalog_id:
                raise CommandValidationError(
                    f"solicitação {request_id} é de outro catálogo ({request.catalog_id})"
                )
            if request.draft_id is not None:
                linked = read_model(scope.tx, "draft", request.draft_id, DraftRecord)
                if linked is not None and linked[0].state not in TERMINAL_DRAFT_STATES:
                    raise InvalidTransitionError(
                        f"solicitação {request_id} já é atendida pelo rascunho ativo "
                        f"{request.draft_id}"
                    )
            target = next_request_state(request.state, "link")
            replace_model(
                scope.tx,
                "request",
                request_id,
                version,
                evolve(request, state=target, draft_id=draft_id),
            )
            scope.emit(
                "request",
                request_id,
                from_state=request.state,
                to_state=target,
                details={"draft_id": draft_id},
            )

    def _move_requests(self, scope: CommandScope, draft_id: str, action: str) -> None:
        """Aplica ``action`` às solicitações atendidas pelo rascunho, quando cabível."""
        for request, version in scan_models(scope.tx, "request", ChangeRequest):
            if request.draft_id != draft_id:
                continue
            if action == "return" and request.state not in _REQUEST_RETURN_STATES:
                continue
            if action != "return" and (request.state, action) not in _REQUEST_TRANSITIONS:
                continue
            target = next_request_state(request.state, action)
            replace_model(
                scope.tx, "request", request.request_id, version, evolve(request, state=target)
            )
            scope.emit(
                "request",
                request.request_id,
                from_state=request.state,
                to_state=target,
                details={"draft_id": draft_id},
            )

    def _withdraw(self, scope: CommandScope, draft: DraftRecord, cause: str) -> None:
        """Invalida aprovação e candidato vigentes e devolve as solicitações à triagem."""
        if draft.approval_id is not None:
            scope.emit(
                "review",
                draft.approval_id,
                from_state="valid",
                to_state="invalidated",
                revision=draft.current_revision,
                reason=cause,
            )
        if draft.candidate_id is not None:
            found = read_model(scope.tx, "candidate", draft.candidate_id, ReleaseCandidate)
            if found is not None and found[0].state == "prepared":
                candidate, version = found
                replace_model(
                    scope.tx,
                    "candidate",
                    candidate.candidate_id,
                    version,
                    evolve(candidate, state="invalidated", closing_reason=cause),
                )
                scope.emit(
                    "candidate",
                    candidate.candidate_id,
                    from_state="prepared",
                    to_state="invalidated",
                    reason=cause,
                )
        if draft.state in ("in_review", "approved"):
            self._move_requests(scope, draft.draft_id, "return")


def _merge_import(base: CatalogContent | None, imported: CatalogContent) -> CatalogContent:
    """Acrescenta o importado ao release-base; entidade publicada não é alterada."""
    if base is None:
        return imported
    entities = index_content(base)
    for kind, entity in imported.iter_entities():
        entity_id = entity_key(entity)
        existing = entities[kind].get(entity_id)
        if existing is None:
            entities[kind][entity_id] = entity
        elif existing != entity:
            raise CommandValidationError(
                f"importação não altera entidade publicada ({kind} {entity_id}); use edição"
            )
    return rebuild_content(entities)
