"""Fachada da área de trabalho do catálogo para a interface (M1-14, E5).

Liga uma interface (o shell Streamlit atual ou a futura API Python da M4) aos serviços
reais já existentes: ``CurationService`` e ``PublicationService`` (E2), autoridade
operacional, ``ProjectService`` e ``CatalogAdoptionService`` (E3) e análises
persistidas. A fachada não tem banco, DTO de identidade nem regra de autorização
próprios: cada comando vira um comando do serviço, com chave idempotente e o
``actor_context_id`` de uma sessão emitida aqui, no backend. A interface nunca informa
papel ou ``actor_kind``; a autorização continua no serviço (``authorize``).

Erros dos serviços viram ``WorkspaceError`` com código estável, mensagem útil e sem
caminhos de disco. Salvar rascunho, aprovar conteúdo, publicar pacote, adotar pin e
aprovar alteração de IFC são ações distintas; esta fachada não escreve IFC.
"""

import functools
import json
import re
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from pydantic import ValidationError

from src.artifacts.curation_adapter import LocalReleaseArtifactStore
from src.artifacts.storage import LocalArtifactStore
from src.domain_catalog.canonical import parse_json_strict
from src.domain_catalog.content import CatalogContent
from src.domain_catalog.contracts import CatalogReleaseRef
from src.domain_catalog.curation import CurationService
from src.domain_catalog.curation_errors import (
    CurationError,
    DraftPatchError,
    RevisionConflictError,
)
from src.domain_catalog.curation_models import (
    CommandMeta,
    CommandOutcome,
    DeprecateEntity,
    DraftHead,
    DraftPatch,
    DuplicateEntity,
    OriginRef,
    RemoveProposal,
    RequestedField,
    ReviewVerdict,
    Severity,
    UpsertEntity,
)
from src.domain_catalog.errors import CatalogError
from src.domain_catalog.migration import CatalogAdoptionService, adoption_command
from src.domain_catalog.migration_contracts import AdoptionIntent, MigrationError
from src.domain_catalog.models import (
    AliasMapping,
    ApplicabilityRule,
    EvidencePolicy,
    IFCBinding,
    LocalizedText,
)
from src.domain_catalog.operations import DEFAULT_OPERATION_REGISTRY, OperationRegistry
from src.domain_catalog.package import ENTITY_MODELS, CatalogIdentity, ComponentTerms, PackageLimits
from src.domain_catalog.publication import PublicationService
from src.domain_catalog.workspace_models import (
    ActionReceipt,
    AdoptionPreview,
    AliasView,
    AnalysisRow,
    AnalysisView,
    AssertionView,
    CandidateSummary,
    CapabilityView,
    CatalogRow,
    CatalogView,
    DecisionView,
    DraftSummary,
    FieldIssue,
    FilterOptions,
    GroupBy,
    HistoryEntry,
    LiteralPair,
    PinView,
    RowDetail,
    RowFilters,
    ValidationView,
    WorkspaceError,
    WorkspaceMode,
    WorkspaceSession,
)
from src.operations.actor_context import ActorContextService
from src.operations.contracts import OperationalError
from src.operations.curation_adapter import SQLiteCurationStore
from src.operations.database import DB_FILE, OperationalStore, StorePurpose
from src.operations.project_models import ProjectRecord
from src.operations.project_service import ProjectService

Value = TypeVar("Value")

EDITABLE_KINDS: frozenset[str] = frozenset(
    {
        "concepts",
        "bindings",
        "applicability_rules",
        "evidence_policies",
        "aliases",
        "units",
        "value_sets",
        "reconciliation_decisions",
    }
)
"""Entidades editáveis pela tabela; fontes e decisões seguem os fluxos próprios."""

DERIVED_FIELDS: frozenset[str] = frozenset({"id", "lifecycle"})
"""Campos não editáveis livremente: identidade e estado cadastral mudam por operação."""

_PATH_PATTERN = re.compile(
    r"(?:(?<![A-Za-z])[A-Za-z]:[\\/]|\\\\|(?<![\w.])/(?:home|Users|tmp|var|mnt|private|opt|etc)/)"
    r"(?:[^\\/:*?\"<>|\r\n]*[\\/])*[^\\/:*?\"<>|\r\n]*"
)
"""Caminho absoluto até ``:``, aspas duplas, ``*?<>|`` ou fim de linha.

Segmentos podem ter espaço (e aspa simples). Omite a mais (o texto depois do caminho na
mesma frase), nunca a menos. Só se aplica a mensagens de erro; dados do modelo IFC/IDS
exibidos na análise não passam por aqui.
"""

_FRIENDLY: Mapping[str, str] = {
    "revision_conflict": (
        "O rascunho mudou desde que você o abriu. Sua edição foi preservada na tela; "
        "confira a revisão atual e reaplique explicitamente."
    ),
    "content_hash_mismatch": (
        "O conteúdo não é mais o da revisão exibida; a confirmação foi recusada sem efeito. "
        "Reabra a revisão atual antes de confirmar."
    ),
    "idempotency_conflict": (
        "Esta chave de comando já foi usada com outro conteúdo; nada foi gravado. "
        "Inicie a ação de novo para gerar outra chave."
    ),
    "actor_not_allowed": "Ação não permitida para este ator, conferido pelo serviço.",
    "actor_context": "Contexto de ator inválido ou desconhecido no serviço.",
    "invalid_transition": "A ação não cabe no estado atual do registro.",
    "invalid_patch": "A alteração foi recusada pela validação; veja os campos indicados.",
    "validation_failed": (
        "A validação automática tem erros; corrija os campos indicados antes de seguir."
    ),
    "invalid_command": "Dados do comando inválidos; confira os campos obrigatórios.",
    "not_found": "Registro não encontrado.",
    "candidate_mismatch": (
        "O candidato não corresponde à versão/hash confirmados; nada foi publicado."
    ),
    "publication_refused": "A publicação foi recusada pelo serviço; nada foi publicado.",
    "base_superseded": (
        "O release-base deste rascunho foi superado por outra publicação. Nada foi "
        "publicado; abra um rascunho sobre o release atual."
    ),
    "publication_in_progress": (
        "Há uma publicação em andamento neste catálogo. Retome-a ou abandone-a "
        "explicitamente antes de iniciar outra."
    ),
    "publication_incomplete": (
        "A publicação foi interrompida antes do recibo; o release não está disponível. "
        "Repita com a mesma chave ou use retomar/abandonar."
    ),
    "artifact_store": (
        "Falha ao gravar artefatos do release; nada ficou disponível. Repita com a mesma "
        "chave depois de conferir o armazenamento."
    ),
    "release_collision": (
        "O destino do release já existe e não foi sobrescrito; consulte a inspeção."
    ),
    "package_error": (
        "Pacote de catálogo inválido ou adulterado: ativação bloqueada, sem catálogo "
        "vazio e sem consulta externa."
    ),
    "store_unavailable": (
        "Armazenamento de curadoria indisponível; nada foi confirmado. Repita com a "
        "mesma chave quando o armazenamento voltar."
    ),
    "store_conflict": "Gravação concorrente detectada; recarregue e tente de novo.",
}


def scrub(text: str) -> str:
    """Remove caminhos absolutos de uma mensagem antes de apresentá-la.

    Cada caminho é omitido inteiro (raiz e todos os segmentos, inclusive com espaços),
    para não expor nomes de pastas abaixo da pasta pessoal, temporária ou do projeto.
    """
    return _PATH_PATTERN.sub("<caminho omitido>", text)


def _issue_view(issue: Any, severity: Severity = "error") -> FieldIssue:
    found: Severity = getattr(issue, "severity", severity)
    return FieldIssue(
        severity=found,
        code=str(issue.code),
        entity_kind=getattr(issue, "entity_kind", None),
        entity_id=getattr(issue, "entity_id", None),
        field=getattr(issue, "field", None),
        message=scrub(str(issue.message)),
    )


def translate(exc: Exception) -> WorkspaceError:
    """Erro de serviço → ``WorkspaceError`` apresentável, sem caminhos nem stack trace."""
    if isinstance(exc, WorkspaceError):
        return exc
    if isinstance(exc, RevisionConflictError):
        current = exc.current if isinstance(exc.current, int) else None
        return WorkspaceError(
            exc.code,
            _FRIENDLY[exc.code]
            + (f" (esperada {exc.expected}, atual {exc.current})." if current else ""),
            current_revision=current,
        )
    if isinstance(exc, DraftPatchError):
        return WorkspaceError(
            exc.code, _FRIENDLY[exc.code], issues=tuple(_issue_view(i) for i in exc.issues)
        )
    if isinstance(exc, CurationError):
        code = getattr(exc, "code", "curation_error")
        retry = code in {"publication_incomplete", "artifact_store", "store_unavailable"}
        detail = scrub(str(exc))
        base = _FRIENDLY.get(code, "A ação foi recusada pelo serviço.")
        return WorkspaceError(code, f"{base} Detalhe: {detail}", retry_same_key=retry)
    if isinstance(exc, MigrationError):
        return WorkspaceError(
            f"adoption_{exc.reason}",
            f"Adoção recusada sem efeito ({exc.reason}). Detalhe: {scrub(str(exc))}",
        )
    if isinstance(exc, OperationalError):
        return WorkspaceError(
            f"operational_{exc.reason}",
            f"Operação recusada sem efeito ({exc.reason}). Detalhe: {scrub(str(exc))}",
            retry_same_key=exc.reason == "store_busy",
        )
    if isinstance(exc, CatalogError):
        code = getattr(exc, "code", "catalog_error")
        base = _FRIENDLY.get(code, "Falha de catálogo; nada foi ativado.")
        return WorkspaceError(code, f"{base} Detalhe: {scrub(str(exc))}")
    if isinstance(exc, ValidationError):
        issues = tuple(
            FieldIssue(
                severity="error",
                code=str(error["type"]),
                entity_kind=None,
                entity_id=None,
                field=".".join(str(part) for part in error["loc"]) or None,
                message=scrub(str(error["msg"])),
            )
            for error in exc.errors()
        )
        return WorkspaceError(
            "invalid_input", "Dados inválidos nos campos indicados.", issues=issues
        )
    if isinstance(exc, (ValueError, LookupError)):
        return WorkspaceError("invalid_input", scrub(str(exc)))
    return WorkspaceError(
        "unexpected", "Falha inesperada; nada foi confirmado pela interface.", retry_same_key=True
    )


def command_entity_id(command_id: str, draft_id: str, role: str) -> str:
    """Deriva ID estável do comando e papel, preservando replay após reinício.

    O serviço continua conferindo ator e hash integral do payload; esta identidade
    não autoriza comandos nem torna pedidos diferentes equivalentes.
    """
    seed = json.dumps([command_id, draft_id, role], ensure_ascii=False)
    return f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, seed)}"


def _uuid(value: str, label: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise WorkspaceError("invalid_input", f"{label} inválido") from exc


def _call(action: Callable[[], Value]) -> Value:
    try:
        return action()
    except WorkspaceError:
        raise
    except Exception as exc:  # toda falha vira mensagem apresentável
        raise translate(exc) from exc


def _text(texts: Sequence[LocalizedText], lang: str = "pt-BR") -> str:
    for text in texts:
        if text.lang == lang:
            return text.text
    return texts[0].text if texts else ""


@dataclass(frozen=True)
class WorkspaceComponents:
    """Serviços reais montados sobre uma raiz local (``db`` e ``a``)."""

    root: Path
    store: OperationalStore
    artifacts: LocalArtifactStore
    releases: LocalReleaseArtifactStore
    actors: ActorContextService
    curation: CurationService
    publication: PublicationService
    projects: ProjectService
    adoption: CatalogAdoptionService
    registry: OperationRegistry


def open_components(
    root: Path,
    *,
    purpose: StorePurpose | None,
    registry: OperationRegistry = DEFAULT_OPERATION_REGISTRY,
    limits: PackageLimits | None = None,
) -> WorkspaceComponents:
    """Abre (ou cria, com ``purpose``) a autoridade e os artefatos sob ``root``."""
    store = OperationalStore.open(root / "db", purpose=purpose)
    artifacts = LocalArtifactStore(root / "a")
    releases = LocalReleaseArtifactStore(artifacts.publication_root())
    curation_store = SQLiteCurationStore(store)
    actors = ActorContextService(store)
    publication = PublicationService(
        curation_store, actors, releases, registry=registry, limits=limits
    )
    curation = CurationService(curation_store, actors, releases=publication, registry=registry)
    return WorkspaceComponents(
        root=root,
        store=store,
        artifacts=artifacts,
        releases=releases,
        actors=actors,
        curation=curation,
        publication=publication,
        projects=ProjectService(store, artifacts),
        adoption=CatalogAdoptionService(store, artifacts, package_limits=limits),
        registry=registry,
    )


def open_operational_workspace(
    root: Path,
    *,
    registry: OperationRegistry = DEFAULT_OPERATION_REGISTRY,
    limits: PackageLimits | None = None,
) -> "CatalogWorkspace":
    """Abre uma área operacional **já inicializada**; nunca cria banco pela interface."""
    if not (root / "db" / DB_FILE).is_file():
        raise WorkspaceError(
            "operational_not_initialized",
            "Área operacional configurada ainda não inicializada; nada foi criado. "
            "Inicialize-a pelo procedimento operacional.",
            keep_input=False,
        )
    components = open_components(root, purpose=None, registry=registry, limits=limits)
    return CatalogWorkspace(components, mode="operational")


class CatalogWorkspace:
    """Consultas e comandos da tela de curadoria, sobre os serviços reais."""

    def __init__(self, components: WorkspaceComponents, *, mode: WorkspaceMode) -> None:
        """Recusa simulação sobre banco operacional e operação sobre banco sintético."""
        expected: StorePurpose = "synthetic_test" if mode == "simulation" else "operational"
        if components.store.purpose != expected:
            raise WorkspaceError(
                "purpose_mismatch",
                f"Modo {mode} exige armazenamento {expected}; recebido "
                f"{components.store.purpose}. Nada foi aberto.",
                keep_input=False,
            )
        self.components = components
        self.mode: WorkspaceMode = mode
        self._sessions: dict[str, WorkspaceSession] = {}

    # --- sessão --------------------------------------------------------------------------

    def open_session(self, declared_name: str | None) -> WorkspaceSession:
        """Registra uma pessoa (``human``) com nome declarado; não autentica ninguém.

        O tipo de ator é fixado aqui, no backend. Assistente e serviço não são criáveis
        pela interface.
        """
        name = (declared_name or "").strip() or None
        context = _call(
            lambda: self.components.actors.register(actor_kind="human", declared_name=name)
        )
        session = WorkspaceSession(
            session_id=str(uuid.uuid4()),
            actor_context_id=context.actor_context_id,
            declared_name=name,
            mode=self.mode,
        )
        self._sessions[session.session_id] = session
        return session

    def _actor(self, session: WorkspaceSession) -> str:
        known = self._sessions.get(session.session_id)
        if known is None or known != session:
            raise WorkspaceError(
                "session_unknown",
                "Sessão não emitida por esta área de trabalho; identifique-se de novo.",
                keep_input=True,
            )
        return known.actor_context_id

    def _meta(self, session: WorkspaceSession, command_id: str) -> CommandMeta:
        return CommandMeta(command_id=command_id, actor_context_id=self._actor(session))

    @staticmethod
    def new_command_id() -> str:
        """Chave idempotente nova; a interface a guarda até a resposta definitiva."""
        return str(uuid.uuid4())

    # --- leitura do conteúdo -------------------------------------------------------------

    def list_releases(self) -> tuple[CatalogReleaseRef, ...]:
        """Releases com recibo de publicação, em ordem de publicação."""
        receipts = _call(self.components.publication.list_published)
        return tuple(receipt.release for receipt in receipts)

    def view_content(self, view: CatalogView) -> CatalogContent:
        """Conteúdo exato do release (reaberto e conferido) ou da revisão do rascunho."""
        if view.kind == "release":
            if view.release is None:
                raise WorkspaceError("invalid_input", "release não informado")
            ref = view.release
            return _call(lambda: self.components.publication.open_published(ref).content)
        if view.draft_id is None:
            raise WorkspaceError("invalid_input", "rascunho não informado")
        draft_id = view.draft_id
        revision = view.revision
        if revision is None:
            revision = _call(lambda: self.components.curation.get_head(draft_id)).revision
        number = revision
        return _call(lambda: self.components.curation.get_revision(draft_id, number).content)

    def catalog_id_of(self, view: CatalogView) -> str:
        """ID do catálogo do conteúdo exibido (release ou rascunho)."""
        if view.kind == "release" and view.release is not None:
            return view.release.catalog_id
        if view.draft_id is None:
            raise WorkspaceError("invalid_input", "rascunho não informado")
        draft_id = view.draft_id
        return _call(lambda: self.components.curation.get_draft(draft_id)).catalog.catalog_id

    def rows(self, view: CatalogView, filters: RowFilters | None = None) -> tuple[CatalogRow, ...]:
        """Linhas da tabela (um uso por linha), filtradas por fonte/classe/perfil/estado."""
        content = self.view_content(view)
        rows = _call(lambda: _rows(content, self.components.registry))
        chosen = filters or RowFilters()
        return tuple(
            row
            for row in rows
            if (chosen.source is None or chosen.source in row.sources)
            and (chosen.entity_class is None or chosen.entity_class in row.entity_classes)
            and (chosen.profile is None or chosen.profile in row.profiles)
            and (chosen.state is None or chosen.state == row.lifecycle)
        )

    def filter_options(self, view: CatalogView) -> FilterOptions:
        """Valores existentes de cada filtro no conteúdo exibido."""
        content = self.view_content(view)
        rows = _call(lambda: _rows(content, self.components.registry))
        return FilterOptions(
            sources=tuple(sorted({s for row in rows for s in row.sources})),
            entity_classes=tuple(sorted({c for row in rows for c in row.entity_classes})),
            profiles=tuple(sorted({p for row in rows for p in row.profiles})),
            states=tuple(sorted({row.lifecycle for row in rows})),
        )

    def detail(self, view: CatalogView, binding_id: str) -> RowDetail:
        """Detalhe do uso: conceito × binding, original × reconciliado e histórico."""
        content = self.view_content(view)
        found = _call(lambda: _rows(content, self.components.registry))
        rows = {row.binding_id: row for row in found}
        if binding_id not in rows:
            raise WorkspaceError("not_found", "uso não encontrado no conteúdo exibido")
        history = self._history(view)
        return _call(lambda: _detail(content, rows[binding_id], history))

    def _history(self, view: CatalogView) -> tuple[HistoryEntry, ...]:
        draft_ids: set[str] = set()
        entries: list[HistoryEntry] = []
        published: tuple[HistoryEntry, ...] = ()
        if view.kind == "draft" and view.draft_id is not None:
            draft_ids.add(view.draft_id)
        elif view.release is not None:
            ref = view.release
            receipt = _call(lambda: self.components.publication.get_publication(ref))
            draft_ids.add(receipt.draft_id)
            published = (
                HistoryEntry(
                    at_utc=receipt.published_at,
                    operation="publish",
                    actor=receipt.published_by.responsible_label,
                    subject=f"release {receipt.release.version}",
                    transition="candidate → published",
                    reason=receipt.publication_justification,
                ),
            )
        for event in _call(self.components.curation.events):
            if event.subject_id in draft_ids or any(
                detail.value in draft_ids for detail in event.details
            ):
                entries.append(
                    HistoryEntry(
                        at_utc=event.at_utc,
                        operation=event.operation,
                        actor=event.actor.responsible_label,
                        subject=f"{event.subject_kind} {event.subject_id}",
                        transition=f"{event.from_state or '—'} → {event.to_state or '—'}",
                        reason=event.reason,
                    )
                )
        if view.kind == "release":
            entries += published
        return tuple(sorted(entries, key=lambda e: e.at_utc))

    def operations(self) -> tuple[CapabilityView, ...]:
        """Operações registradas no código instalado; só estas habilitam cadastro de uso."""
        return tuple(
            _capability(self.components.registry, op, None)
            for op in self.components.registry.operation_ids
        )

    # --- solicitações --------------------------------------------------------------------

    def request_change(
        self,
        session: WorkspaceSession,
        *,
        command_id: str,
        catalog_id: str,
        motivation: str,
        field: RequestedField,
        origin_refs: Sequence[OriginRef] = (),
    ) -> ActionReceipt:
        """Solicitação de operador: registra demanda, sem equivalência nem release."""
        outcome = _call(
            lambda: self.components.curation.request_change(
                self._meta(session, command_id),
                catalog_id=catalog_id,
                motivation=motivation,
                field=field,
                origin_refs=origin_refs,
            )
        )
        return _receipt(outcome, "Solicitação registrada; nenhuma equivalência foi criada.")

    def list_requests(self, state: str | None = None) -> tuple[Any, ...]:
        """Solicitações em ordem de registro."""
        return _call(lambda: self.components.curation.list_requests(state=state))

    def act_on_request(
        self,
        session: WorkspaceSession,
        *,
        command_id: str,
        request_id: str,
        action: str,
        reason: str,
    ) -> ActionReceipt:
        """Triagem, rejeição (com justificativa) ou cancelamento de solicitação."""
        service = self.components.curation
        meta = self._meta(session, command_id)
        handlers: dict[str, Callable[[], CommandOutcome[Any]]] = {
            "triage": lambda: service.triage_request(meta, request_id=request_id, reason=reason),
            "reject": lambda: service.reject_request(
                meta, request_id=request_id, justification=reason
            ),
            "cancel": lambda: service.cancel_request(meta, request_id=request_id, reason=reason),
        }
        if action not in handlers:
            raise WorkspaceError("invalid_input", f"ação desconhecida: {action}")
        outcome = _call(handlers[action])
        return _receipt(outcome, f"Solicitação: {action} registrada.")

    # --- rascunhos -----------------------------------------------------------------------

    def list_drafts(self) -> tuple[DraftSummary, ...]:
        """Rascunhos com revisão/hash atuais, para confirmações exatas."""
        summaries = []
        for draft in _call(self.components.curation.list_drafts):
            head = _call(functools.partial(self.components.curation.get_head, draft.draft_id))
            summaries.append(
                DraftSummary(
                    draft_id=draft.draft_id,
                    title=draft.title,
                    state=draft.state,
                    revision=head.revision,
                    content_sha256=head.content_sha256,
                    base_release=draft.base_release,
                    candidate_id=draft.candidate_id,
                    published_release=draft.published_release,
                )
            )
        return tuple(summaries)

    def create_draft(
        self,
        session: WorkspaceSession,
        *,
        command_id: str,
        title: str,
        reason: str,
        base_release: CatalogReleaseRef | None = None,
        catalog: CatalogIdentity | None = None,
        request_ids: Sequence[str] = (),
    ) -> ActionReceipt:
        """Rascunho vazio (primeiro release) ou sobre o último release publicado."""
        outcome = _call(
            lambda: self.components.curation.create_draft(
                self._meta(session, command_id),
                title=title,
                reason=reason,
                catalog=catalog,
                base_release=base_release,
                request_ids=request_ids,
            )
        )
        return _receipt(outcome, "Rascunho salvo; nada foi publicado nem adotado.")

    def start_catalog(
        self,
        session: WorkspaceSession,
        *,
        command_id: str,
        name: str,
        namespace: str,
        maintainer: str,
        title: str,
        reason: str,
        candidates: bytes | None = None,
        source_label: str = "",
    ) -> ActionReceipt:
        """Inicia catálogo vazio ou importa candidatos locais como rascunho.

        Entrada é conteúdo exportado do staging/catálogo, nunca caminho executável.
        Limite de 8 MiB, parser estrito e contratos E2; nada é aprovado/publicado.
        """
        self._actor(session)
        identity = _call(
            lambda: CatalogIdentity(
                catalog_id=command_entity_id(command_id, namespace, "catalog"),
                namespace=namespace,
                namespace_status="provisional",
                name=name,
                maintainer=maintainer,
                language="pt-BR",
            )
        )
        if candidates is None:
            return self.create_draft(
                session, command_id=command_id, title=title, reason=reason, catalog=identity
            )
        if len(candidates) > 8 * 1024 * 1024:
            raise WorkspaceError("input_limit", "Arquivo excede o limite de 8 MiB.")
        content = _call(
            lambda: CatalogContent.model_validate(parse_json_strict(candidates.decode("utf-8")))
        )
        outcome = _call(
            lambda: self.components.curation.import_draft(
                self._meta(session, command_id),
                title=title,
                catalog=identity,
                content=content,
                source_label=source_label,
                reason=reason,
            )
        )
        return _receipt(outcome, "Candidatos importados como rascunho; revisão humana pendente.")

    def add_entity(
        self,
        session: WorkspaceSession,
        *,
        command_id: str,
        draft_id: str,
        expected_revision: int,
        kind: str,
        fields: Mapping[str, Any],
        reason: str,
    ) -> ActionReceipt:
        """Propõe conceito distinto, unidade, domínio, alias ou decisão rastreável."""
        if kind not in {"concepts", "units", "value_sets", "aliases", "reconciliation_decisions"}:
            raise WorkspaceError("invalid_input", "Entidade não disponível para autoria.")
        if DERIVED_FIELDS & set(fields):
            raise WorkspaceError("derived_field", "Identidade e estado são derivados pelo serviço.")
        data = {**fields, "id": command_entity_id(command_id, draft_id, kind)}
        if kind != "reconciliation_decisions":
            data["lifecycle"] = "draft"
        entity = _call(lambda: ENTITY_MODELS[kind].model_validate(data))
        return self._edit(
            session,
            command_id,
            draft_id,
            expected_revision,
            [_upsert(kind, entity)],
            reason,
            "Proposta salva; requer validação e revisão do conteúdo exato.",
        )

    def _edit(
        self,
        session: WorkspaceSession,
        command_id: str,
        draft_id: str,
        expected_revision: int,
        operations: Sequence[Any],
        reason: str,
        message: str,
    ) -> ActionReceipt:
        patch = _call(lambda: DraftPatch(operations=tuple(operations), reason=reason))
        outcome = _call(
            lambda: self.components.curation.edit_draft(
                self._meta(session, command_id),
                draft_id=draft_id,
                expected_revision=expected_revision,
                patch=patch,
            )
        )
        return _receipt(outcome, message)

    def add_usage(
        self,
        session: WorkspaceSession,
        *,
        command_id: str,
        draft_id: str,
        expected_revision: int,
        concept_id: str,
        entity_classes: Sequence[str],
        include_subtypes: bool,
        schemas: Sequence[str],
        carrier_kind: str,
        set_name: str | None,
        field_name: str,
        ifc_type: str | None,
        scope: str,
        reason: str,
        set_kind: str | None = None,
        evidence_policy_id: str | None = None,
        operation_id: str | None = None,
        operation_version: str | None = None,
        channels: Sequence[str] = ("P",),
        source_assertion_ids: Sequence[str] = (),
    ) -> ActionReceipt:
        """Novo uso de um conceito existente com operação já implementada (UC02/UC04).

        Cria regra de aplicabilidade e binding em ``draft`` apontando o **mesmo**
        conceito. A política de evidência é uma existente ou uma nova sobre operação
        registrada no código; operação ausente é recusada aqui e deve virar
        solicitação (UC05), sem cadastro de executor inexistente.
        """
        if evidence_policy_id is not None and operation_id is not None:
            raise WorkspaceError(
                "invalid_input", "escolha política existente ou operação, não ambas"
            )
        operations: list[Any] = []
        policy_id = evidence_policy_id
        if evidence_policy_id is not None:
            content = self.view_content(
                CatalogView(kind="draft", draft_id=draft_id, revision=expected_revision)
            )
            chosen = next(
                (p for p in content.evidence_policies if p.id == evidence_policy_id), None
            )
            if chosen is None:
                raise WorkspaceError("not_found", "política de evidência não encontrada")
            self._require_available(chosen.operation_id, chosen.operation_version)
        if operation_id is not None:
            capability = self.components.registry.capability(operation_id, operation_version)
            if capability.status != "available":
                raise WorkspaceError(
                    "operation_unavailable",
                    f"Operação {operation_id} indisponível ({capability.status}): "
                    "registre uma solicitação de nova operação; nenhum cadastro foi feito.",
                )
            policy_id = command_entity_id(command_id, draft_id, "usage-policy")
            policy = _call(
                lambda: EvidencePolicy.model_validate(
                    {
                        "id": policy_id,
                        "operation_id": operation_id,
                        "operation_version": operation_version or capability.available_version,
                        "admissible_channels": tuple(channels),
                        "on_missing": "abstain",
                        "on_conflict": "abstain",
                        "source_assertion_ids": tuple(source_assertion_ids),
                        "lifecycle": "draft",
                    }
                )
            )
            operations.append(_upsert("evidence_policies", policy))
        rule_id = command_entity_id(command_id, draft_id, "usage-rule")
        rule = _call(
            lambda: ApplicabilityRule.model_validate(
                {
                    "id": rule_id,
                    "entity_classes": tuple(entity_classes),
                    "include_subtypes": include_subtypes,
                    "source_assertion_ids": tuple(source_assertion_ids),
                    "lifecycle": "draft",
                }
            )
        )
        binding = _call(
            lambda: IFCBinding.model_validate(
                {
                    "id": command_entity_id(command_id, draft_id, "usage-binding"),
                    "concept_id": concept_id,
                    "applicability_rule_id": rule_id,
                    "declared_schemas": tuple(schemas),
                    "carrier_kind": carrier_kind,
                    "set_name": set_name or None,
                    "set_kind": set_kind,
                    "field_name": field_name,
                    "ifc_type": ifc_type or None,
                    "scope": scope,
                    "carrier_status": "approved",
                    "evidence_policy_id": policy_id,
                    "write_enabled": False,
                    "source_assertion_ids": tuple(source_assertion_ids),
                    "lifecycle": "draft",
                }
            )
        )
        operations += [_upsert("applicability_rules", rule), _upsert("bindings", binding)]
        return self._edit(
            session,
            command_id,
            draft_id,
            expected_revision,
            operations,
            reason,
            "Uso proposto em rascunho (mesmo conceito); requer validação, revisão e "
            "publicação. Escrita no IFC continua desligada.",
        )

    def _require_available(self, operation_id: object, version: object) -> None:
        """Recusa política sobre operação não registrada (ou de outra versão) no código."""
        requested = str(operation_id)
        capability = self.components.registry.capability(
            requested, None if version is None else str(version)
        )
        if capability.status != "available":
            raise WorkspaceError(
                "operation_unavailable",
                f"Operação {requested} indisponível ({capability.status}): registre uma "
                "solicitação de nova operação; nada foi salvo.",
            )

    def duplicate_usage(
        self,
        session: WorkspaceSession,
        *,
        command_id: str,
        draft_id: str,
        expected_revision: int,
        binding_id: str,
        reason: str,
    ) -> ActionReceipt:
        """Duplica a linha: novo binding em ``draft`` com o **mesmo** conceito.

        A cópia nasce idêntica exceto pelo ID e a validação a recusa até a revisão de
        identidade (fonte, aplicabilidade, operação); não publica nada.
        """
        operation = _call(
            lambda: DuplicateEntity(
                op="duplicate",
                kind="bindings",
                source_id=binding_id,
                new_id=command_entity_id(command_id, draft_id, "duplicate-binding"),
            )
        )
        return self._edit(
            session,
            command_id,
            draft_id,
            expected_revision,
            [operation],
            reason,
            "Linha duplicada em rascunho; revise a identidade antes de submeter.",
        )

    def edit_entity(
        self,
        session: WorkspaceSession,
        *,
        command_id: str,
        draft_id: str,
        expected_revision: int,
        kind: str,
        entity_id: str,
        changes: Mapping[str, Any],
        reason: str,
    ) -> ActionReceipt:
        """Edita campos de uma entidade da revisão esperada; vira proposta ``draft``."""
        if kind not in EDITABLE_KINDS:
            raise WorkspaceError("invalid_input", f"entidade {kind} não é editável pela tabela")
        derived = sorted(DERIVED_FIELDS & set(changes))
        if derived:
            raise WorkspaceError(
                "derived_field",
                f"campos derivados não são editáveis livremente: {', '.join(derived)}",
                issues=tuple(
                    FieldIssue(
                        severity="error",
                        code="derived_field",
                        entity_kind=kind,
                        entity_id=entity_id,
                        field=name,
                        message="mude identidade/estado pelas operações próprias",
                    )
                    for name in derived
                ),
            )
        content = self.view_content(
            CatalogView(kind="draft", draft_id=draft_id, revision=expected_revision)
        )
        current = {_entity_id(e): e for e in getattr(content, kind)}
        if entity_id not in current:
            raise WorkspaceError("not_found", "entidade não encontrada na revisão esperada")
        data = {**current[entity_id].model_dump(mode="json"), **changes}
        if kind != "reconciliation_decisions":
            data["lifecycle"] = "draft"
        if kind == "evidence_policies" and {"operation_id", "operation_version"} & set(changes):
            self._require_available(data.get("operation_id"), data.get("operation_version"))
        operation = _call(lambda: UpsertEntity(op="upsert", kind=kind, entity=data))  # type: ignore[arg-type]
        return self._edit(
            session,
            command_id,
            draft_id,
            expected_revision,
            [operation],
            reason,
            "Rascunho salvo como nova revisão; aprovações anteriores deixam de valer.",
        )

    def withdraw_proposal(
        self,
        session: WorkspaceSession,
        *,
        command_id: str,
        draft_id: str,
        expected_revision: int,
        kind: str,
        entity_id: str,
        reason: str,
    ) -> ActionReceipt:
        """Retira proposta do rascunho (entidade publicada volta à versão do release)."""
        operation = _call(
            lambda: RemoveProposal(op="remove", kind=kind, entity_id=entity_id)  # type: ignore[arg-type]
        )
        return self._edit(
            session,
            command_id,
            draft_id,
            expected_revision,
            [operation],
            reason,
            "Proposta retirada.",
        )

    def deprecate(
        self,
        session: WorkspaceSession,
        *,
        command_id: str,
        draft_id: str,
        expected_revision: int,
        kind: str,
        entity_id: str,
        reason: str,
    ) -> ActionReceipt:
        """Propõe depreciar entidade publicada; o histórico continua consultável."""
        operation = _call(
            lambda: DeprecateEntity(op="deprecate", kind=kind, entity_id=entity_id)  # type: ignore[arg-type]
        )
        return self._edit(
            session,
            command_id,
            draft_id,
            expected_revision,
            [operation],
            reason,
            "Depreciação proposta em rascunho; nada sai do release publicado.",
        )

    def validation(self, draft_id: str, revision: int | None = None) -> ValidationView:
        """Validação automática da revisão exata, com problemas por entidade/campo."""
        report = _call(lambda: self.components.curation.validate_draft(draft_id, revision))
        summary = report.summary()
        return ValidationView(
            draft_id=report.draft_id,
            revision=report.revision,
            content_sha256=report.content_sha256,
            errors=summary.errors,
            warnings=summary.warnings,
            pending=summary.pending,
            issues=tuple(_issue_view(finding) for finding in report.findings),
        )

    def revision_diff(self, draft_id: str, revision: int | None = None) -> tuple[str, ...]:
        """Mudanças da revisão sobre o release-base, para revisão lado a lado."""
        diff = _call(lambda: self.components.curation.diff_revision(draft_id, revision))
        return (
            *(f"+ {ref}" for ref in diff.added),
            *(f"~ {ref}" for ref in diff.changed),
            *(f"- {ref} (depreciação)" for ref in diff.deprecated),
        )

    def revisions(self, draft_id: str) -> tuple[tuple[int, str, str, str], ...]:
        """Revisões (número, origem, motivo, hash), da primeira à atual."""
        return tuple(
            (r.revision, r.origin, r.reason, r.content_sha256)
            for r in _call(lambda: self.components.curation.list_revisions(draft_id))
        )

    def reviews(self, draft_id: str) -> tuple[str, ...]:
        """Revisões humanas registradas (inclusive invalidadas), em texto apresentável."""
        return tuple(
            f"r{r.revision} {r.verdict} por {r.reviewer.responsible_label} em "
            f"{r.reviewed_at}: {r.justification}"
            for r in _call(lambda: self.components.curation.list_reviews(draft_id))
        )

    def submit_for_review(
        self,
        session: WorkspaceSession,
        *,
        command_id: str,
        draft_id: str,
        revision: int,
        content_sha256: str,
        reason: str,
    ) -> ActionReceipt:
        """Leva a revisão exata (número e hash exibidos) à revisão humana."""
        outcome = _call(
            lambda: self.components.curation.submit_for_review(
                self._meta(session, command_id),
                draft_id=draft_id,
                revision=revision,
                content_sha256=content_sha256,
                reason=reason,
            )
        )
        return _receipt(outcome, "Revisão exata enviada para revisão humana.")

    def review(
        self,
        session: WorkspaceSession,
        *,
        command_id: str,
        draft_id: str,
        revision: int,
        content_sha256: str,
        verdict: ReviewVerdict,
        justification: str,
    ) -> ActionReceipt:
        """Decisão humana sobre a revisão exata; aprovar conteúdo não publica nem adota."""
        outcome = _call(
            lambda: self.components.curation.review_draft(
                self._meta(session, command_id),
                draft_id=draft_id,
                revision=revision,
                content_sha256=content_sha256,
                verdict=verdict,
                justification=justification,
            )
        )
        return _receipt(
            outcome,
            f"Revisão registrada ({verdict}) para a revisão {revision}; nada foi publicado.",
        )

    # --- publicação ----------------------------------------------------------------------

    def candidate(self, candidate_id: str) -> CandidateSummary:
        """Candidato com versão, hash do manifesto, pendências e diff."""
        found = _call(lambda: self.components.publication.get_candidate(candidate_id))
        return CandidateSummary(
            candidate_id=found.candidate_id,
            draft_id=found.draft_id,
            revision=found.revision,
            version=found.release.version,
            manifest_sha256=found.release.manifest_sha256,
            state=found.state,
            pending_items=tuple(
                f"{p.kind}: {p.entity_id} — {p.detail}" for p in found.pending_items
            ),
            pending_ids=tuple(p.entity_id for p in found.pending_items),
            added=found.diff.added,
            changed=found.diff.changed,
            deprecated=found.diff.deprecated,
        )

    def prepare_release(
        self,
        session: WorkspaceSession,
        *,
        command_id: str,
        draft_id: str,
        revision: int,
        content_sha256: str,
        version: str,
        terms: Sequence[ComponentTerms],
        reason: str,
    ) -> ActionReceipt:
        """Monta e reabre o candidato da revisão aprovada; não publica."""
        outcome = _call(
            lambda: self.components.publication.prepare_release(
                self._meta(session, command_id),
                draft_id=draft_id,
                revision=revision,
                content_sha256=content_sha256,
                version=version,
                terms=terms,
                reason=reason,
            )
        )
        return _receipt(outcome, "Candidato preparado e reaberto; ainda não publicado.")

    def publish(
        self,
        session: WorkspaceSession,
        *,
        command_id: str,
        candidate_id: str,
        version: str,
        manifest_sha256: str,
        justification: str,
        acknowledged_pending: Sequence[str] = (),
    ) -> ActionReceipt:
        """Publica o candidato exato confirmado (versão e hash exibidos) por pessoa.

        Nenhum projeto adota o release automaticamente.
        """
        outcome = _call(
            lambda: self.components.publication.publish(
                self._meta(session, command_id),
                candidate_id=candidate_id,
                version=version,
                manifest_sha256=manifest_sha256,
                justification=justification,
                acknowledged_pending=acknowledged_pending,
            )
        )
        return _receipt(outcome, "Release publicado com recibo; nenhum projeto mudou de pin.")

    def publication_inspection(self) -> tuple[str, ...]:
        """Intenções e resíduos de publicação, para retomar ou abandonar explicitamente."""
        found = _call(self.components.publication.inspect)
        lines = [
            f"intenção pendente {i.intent_id}: release {i.release.version} "
            f"(preparo {'válido' if i.staged_valid else 'ausente/inválido'}, "
            f"promovido {'sim' if i.promoted else 'não'})"
            for i in found.pending_intents
        ]
        lines += [
            f"resíduo de preparo ({r.state}): {r.candidate_id}" for r in found.residual_staging
        ]
        lines += [f"preparo órfão: {scrub(path)}" for path in found.orphan_staging]
        lines += [f"publicação danificada: {scrub(text)}" for text in found.damaged_publications]
        lines += [f"release sem recibo: {scrub(text)}" for text in found.unregistered_releases]
        if not found.artifact_store_operational:
            lines.append("armazenamento de artefatos não operacional")
        return tuple(lines)

    def pending_intents(self) -> tuple[tuple[str, str], ...]:
        """Intenções de publicação pendentes (ID, versão), para retomar ou abandonar."""
        found = _call(self.components.publication.inspect)
        return tuple((i.intent_id, i.release.version) for i in found.pending_intents)

    def resume_publication(
        self, session: WorkspaceSession, *, command_id: str, intent_id: str, reason: str
    ) -> ActionReceipt:
        """Conclui publicação interrompida, conferindo intenção e bytes."""
        outcome = _call(
            lambda: self.components.publication.resume_publication(
                self._meta(session, command_id), intent_id=intent_id, reason=reason
            )
        )
        return _receipt(outcome, "Publicação retomada e concluída com recibo.")

    def abandon_publication(
        self, session: WorkspaceSession, *, command_id: str, intent_id: str, reason: str
    ) -> ActionReceipt:
        """Abandona publicação interrompida; bytes sem recibo vão à quarentena."""
        outcome = _call(
            lambda: self.components.publication.abandon_publication(
                self._meta(session, command_id), intent_id=intent_id, reason=reason
            )
        )
        return _receipt(outcome, "Publicação abandonada; o candidato pode ser republicado.")

    def command_status(self, command_id: str) -> str:
        """Estado conhecido de um comando, para resolver resposta perdida sem repetir."""
        record = _call(lambda: self.components.curation.get_command(command_id))
        return "desconhecido" if record is None else record.state

    # --- projeto, pin, diff/impacto, adoção e rollback -----------------------------------

    def list_projects(self) -> tuple[tuple[str, str], ...]:
        """Projetos (ID, nome) da autoridade operacional."""

        def scan() -> tuple[tuple[str, str], ...]:
            with self.components.store.transaction() as uow:
                rows = uow.projects.scan()
            records = [ProjectRecord.model_validate(row.document) for row in rows]
            return tuple(
                (str(r.project_id), r.name) for r in sorted(records, key=lambda r: r.created_at_utc)
            )

        return _call(scan)

    def pin_view(self, project_id: str) -> PinView:
        """Pin vigente e todas as revisões de pin do projeto, sem "latest"."""
        pid = _uuid(project_id, "projeto")
        state = _call(lambda: self.components.projects.load_project_state(pid))

        def history() -> tuple[str, ...]:
            with self.components.store.transaction() as uow:
                rows = uow.pins.scan_revisions(project_id=project_id)
            lines = []
            for row in sorted(rows, key=lambda r: r.document["pin_revision"]):
                doc = row.document
                lines.append(
                    f"pin r{doc['pin_revision']}: {doc['catalog']['version']} "
                    f"({doc['catalog']['manifest_sha256'][:12]}…) — {doc['reason']}"
                )
            return tuple(lines)

        pin = state.pin
        return PinView(
            project_id=project_id,
            project_name=state.project.name,
            pin_revision=state.pin_revision,
            pair_set_revision=state.pair_set_revision,
            catalog=None if pin is None else pin.catalog,
            adopted_by=None if pin is None else pin.actor_snapshot.responsible_label,
            reason=None if pin is None else pin.reason,
            pairs=tuple(f"{p.discipline} (par r{p.pair_revision})" for p in state.pairs),
            history=_call(history),
        )

    def preview_adoption(
        self,
        session: WorkspaceSession,
        *,
        project_id: str,
        target: CatalogReleaseRef,
        intent: AdoptionIntent,
        reason: str,
    ) -> AdoptionPreview:
        """Plano persistido com diff/impacto; não muda pin nem enfileira análise."""
        from src.validation.analysis_identity import current_execution_profile

        actor = _uuid(self._actor(session), "ator")
        pid = _uuid(project_id, "projeto")
        state = _call(lambda: self.components.projects.load_project_state(pid))
        plan = _call(
            lambda: self.components.adoption.prepare_catalog_adoption(
                project_id=pid,
                expected_pin_revision=state.pin_revision,
                expected_pair_set_revision=state.pair_set_revision,
                target_ref=target,
                target_dir=self.components.releases.release_path(target),
                intent=intent,
                reason=reason,
                execution_profile=current_execution_profile(),
                prepared_by_actor_context_id=actor,
            )
        )
        diff_lines: list[str] = []
        impact_lines: list[str] = []
        if plan.diff is not None:
            for change in plan.diff.entity_changes:
                fields = (
                    ", ".join(f"{f.field} [{'/'.join(f.categories)}]" for f in change.fields) or "—"
                )
                diff_lines.append(
                    f"{change.change_kind} {change.entity.kind}:{change.entity.id} — {fields}"
                )
            diff_lines += [
                f"manifesto: {m.field} [{m.category}]" for m in plan.diff.manifest_changes
            ]
            impact_lines = sorted(
                {
                    f"{t.origin.kind}:{t.origin.id} → {t.target.kind}:{t.target.id} ({t.snapshot})"
                    for t in plan.diff.impacts
                }
            )
        return AdoptionPreview(
            plan_id=str(plan.plan_id),
            plan_sha256=self.components.adoption.plan_sha256(plan),
            intent=plan.intent,
            old_catalog=plan.old_ref,
            target_catalog=plan.target_ref,
            diff_lines=tuple(diff_lines),
            diff_absent_reason=plan.diff_absent_reason,
            impact_lines=tuple(impact_lines),
            reanalysis_scope=plan.reanalysis_scope,
            pairs=len(plan.pairs),
            statement=(
                "Confirmar troca o pin do projeto e enfileira nova análise de todos os "
                "pares ativos; análises e aprovações anteriores continuam no histórico e "
                "não são transportadas."
            ),
        )

    def apply_adoption(
        self,
        session: WorkspaceSession,
        *,
        command_id: str,
        project_id: str,
        plan_id: str,
        plan_sha256: str,
    ) -> ActionReceipt:
        """Confirma o plano exato (ID e hash exibidos): novo pin e reanálise enfileirada."""
        actor = _uuid(self._actor(session), "ator")
        key, pid, plan = (
            _uuid(command_id, "chave de comando"),
            _uuid(project_id, "projeto"),
            _uuid(plan_id, "plano"),
        )
        before = _call(lambda: self.components.projects.load_project_state(pid)).pin_revision
        receipt = _call(
            lambda: self.components.adoption.apply_catalog_adoption(
                command=adoption_command(key, actor, pid, plan, plan_sha256),
                plan_id=plan,
                confirmed_plan_sha256=plan_sha256,
            )
        )
        pin = receipt.pin
        replayed = receipt.status == "applied" and pin is not None and pin.pin_revision <= before
        if replayed:
            message = "(repetição idempotente: recibo original) Plano já aplicado por esta chave."
        elif receipt.status == "noop":
            message = "Pin mantido (sem mudança); nenhuma análise nova."
        else:
            message = (
                f"Pin atualizado; {len(receipt.queued_analysis_ids)} análise(s) nova(s) "
                "enfileirada(s). Nenhuma aprovação anterior foi transportada."
            )
        return ActionReceipt(
            command_id=command_id,
            operation=f"adoption_{receipt.intent}",
            subject=f"projeto {project_id}",
            revision=None if pin is None else pin.pin_revision,
            replayed=replayed,
            message=message,
        )

    def list_analyses(self, project_id: str) -> tuple[tuple[str, str, int], ...]:
        """Análises do projeto (ID, estado, revisão do pin), em ordem de enfileiramento."""
        pid = _uuid(project_id, "projeto")
        runs = _call(lambda: self.components.adoption.list_runs(pid))
        return tuple((str(r.analysis_id), r.state, r.identity.pin_revision or 0) for r in runs)

    def execute_queued_analyses(
        self, session: WorkspaceSession, project_id: str
    ) -> tuple[str, ...]:
        """Executa as análises enfileiradas do projeto pelo pipeline E3 (somente leitura).

        Diagnóstico IDS, anexo do catálogo fixado e enriquecimento determinístico; o IFC
        não é alterado e nenhuma proposta é aprovada. Repetir devolve o recibo gravado.
        Exige sessão emitida aqui; a execução é registrada pelo ator de sistema da E3
        (o executor não recebe ator humano), limitação declarada.
        """
        self._actor(session)
        pid = _uuid(project_id, "projeto")
        from src.suggestion_engine.catalog_operations import build_e3_operation_bundle
        from src.validation.catalog_analysis import CatalogAnalysisRequest, execute_catalog_analysis

        bundle = build_e3_operation_bundle()
        runs = _call(lambda: self.components.adoption.list_runs(pid))
        lines: list[str] = []
        for run in runs:
            if run.state != "queued":
                continue
            request = CatalogAnalysisRequest(
                analysis_id=run.analysis_id,
                command_id=uuid.uuid4(),
                expected_identity_sha256=run.identity.digest(),
            )
            receipt = _call(
                functools.partial(
                    execute_catalog_analysis,
                    request,
                    store=self.components.store,
                    artifacts=self.components.artifacts,
                    operation_bundle=bundle,
                )
            )
            problems = ", ".join(p.code for p in receipt.problems) or "nenhum"
            lines.append(f"análise {receipt.analysis_id}: {receipt.state} (problemas: {problems})")
        return tuple(lines)

    def analysis_view(self, analysis_id: str, group_by: GroupBy = "element") -> AnalysisView:
        """Estados IDS, de mapeamento e de evidência separados; esperado/encontrado/origem."""
        from src.validation.catalog_analysis import load_analysis

        aid = _uuid(analysis_id, "análise")
        stored = _call(lambda: load_analysis(self.components.store, aid))
        run = stored.run
        limitations: list[str] = []
        rows: list[AnalysisRow] = []
        if stored.snapshot is None:
            limitations.append(f"análise em estado {run.state}: sem diagnóstico persistido")
        else:
            rows = _analysis_rows(stored)
            limitations += [f"{p.code}: {scrub(p.message)}" for p in stored.snapshot.problems]
        key = (
            (lambda r: (r.element, r.requirement))
            if group_by == "element"
            else (lambda r: (r.requirement, r.element))
        )
        return AnalysisView(
            analysis_id=analysis_id,
            state=run.state,
            catalog=run.identity.catalog_ref,
            pin_revision=run.identity.pin_revision or 0,
            group_by=group_by,
            rows=tuple(sorted(rows, key=key)),
            limitations=tuple(limitations),
        )


# --- projeções ----------------------------------------------------------------------------


def _entity_id(entity: Any) -> str:
    return str(entity.id)


def _upsert(kind: str, entity: Any) -> UpsertEntity:
    return UpsertEntity(op="upsert", kind=kind, entity=entity.model_dump(mode="json"))  # type: ignore[arg-type]


def _receipt(outcome: CommandOutcome[Any], message: str) -> ActionReceipt:
    receipt = outcome.receipt
    return ActionReceipt(
        command_id=receipt.command_id,
        operation=receipt.operation,
        subject=f"{receipt.subject_kind} {receipt.subject_id}",
        revision=receipt.revision,
        replayed=outcome.replayed,
        message=("(repetição idempotente: recibo original) " if outcome.replayed else "") + message,
    )


def _capability(
    registry: OperationRegistry, operation_id: str | None, version: str | None
) -> CapabilityView:
    if operation_id is None:
        return CapabilityView(
            state="no_policy",
            reason="sem política de evidência: nenhum enriquecimento para este uso",
        )
    found = registry.capability(operation_id, version)
    return CapabilityView(
        state=found.status,
        operation_id=found.operation_id,
        requested_version=found.requested_version,
        available_version=found.available_version,
        reason=found.reason,
    )


MISSING = "(referência ausente no rascunho)"
"""Rótulo de conceito citado por um uso mas ausente: a linha aparece, a validação acusa."""


def _rows(content: CatalogContent, registry: OperationRegistry) -> list[CatalogRow]:
    concepts = {c.id: c for c in content.concepts}
    rules = {r.id: r for r in content.applicability_rules}
    policies = {p.id: p for p in content.evidence_policies}
    assertions = {a.id: a for a in content.source_assertions}
    profiles: dict[str, set[str]] = {}
    for membership in content.profile_memberships:
        profiles.setdefault(membership.binding_id, set()).add(membership.profile_id)
    shared: dict[str, int] = {}
    for binding in content.bindings:
        shared[binding.concept_id] = shared.get(binding.concept_id, 0) + 1
    rows: list[CatalogRow] = []
    for binding in sorted(content.bindings, key=lambda b: b.id):
        concept = concepts.get(binding.concept_id)
        rule = rules.get(binding.applicability_rule_id)
        policy = policies.get(binding.evidence_policy_id or "")
        cited: list[str] = [
            *binding.source_assertion_ids,
            *(() if concept is None else concept.source_assertion_ids),
        ]
        if rule is not None:
            cited += rule.source_assertion_ids
        if policy is not None:
            cited += policy.source_assertion_ids
        sources = sorted({assertions[a].source_artifact_id for a in cited if a in assertions})
        rows.append(
            CatalogRow(
                binding_id=binding.id,
                concept_id=binding.concept_id,
                concept_code=MISSING if concept is None else concept.code,
                concept_label=MISSING if concept is None else _text(concept.labels),
                set_name=binding.set_name,
                field_name=binding.field_name,
                carrier_kind=binding.carrier_kind,
                carrier_status=binding.carrier_status,
                scope=binding.scope,
                ifc_type=binding.ifc_type,
                entity_classes=() if rule is None else tuple(rule.entity_classes),
                schemas=tuple(binding.declared_schemas),
                profiles=tuple(sorted(profiles.get(binding.id, set()))),
                sources=tuple(sources),
                lifecycle=binding.lifecycle,
                write_enabled=binding.write_enabled,
                capability=_capability(
                    registry,
                    None if policy is None else policy.operation_id,
                    None if policy is None else policy.operation_version,
                ),
                concept_shared_by=shared[binding.concept_id],
            )
        )
    return rows


def _alias_view(alias: AliasMapping) -> AliasView:
    scope = alias.scope
    parts = [
        f"conjuntos={list(scope.set_names)}" if scope.set_names else "",
        f"classes={list(scope.entity_classes)}" if scope.entity_classes else "",
        f"schemas={list(scope.schemas)}" if scope.schemas else "",
    ]
    return AliasView(
        alias_id=alias.id,
        term=alias.term,
        purpose=alias.purpose,
        scope="; ".join(p for p in parts if p) or "global",
        target=f"binding {alias.target_binding_id}"
        if alias.target_binding_id
        else f"conceito {alias.target_concept_id}",
        lifecycle=alias.lifecycle,
    )


def _locator(assertion: Any) -> str:
    loc = assertion.locator
    parts = [
        f"p. impressa {loc.printed_page}" if loc.printed_page else "",
        f"p. PDF {loc.pdf_page}" if loc.pdf_page else "",
        f"tabela {loc.table}" if loc.table else "",
        f"linha {loc.row_ref}" if loc.row_ref else "",
        f"XML {loc.xml_path}" if loc.xml_path else "",
    ]
    return ", ".join(p for p in parts if p) or "—"


def _detail(content: CatalogContent, row: CatalogRow, history: Iterable[HistoryEntry]) -> RowDetail:
    binding = next(b for b in content.bindings if b.id == row.binding_id)
    concept = next((c for c in content.concepts if c.id == binding.concept_id), None)
    if concept is None:
        raise WorkspaceError(
            "dangling_reference",
            "O uso cita um conceito ausente nesta revisão; retire a proposta ou corrija o "
            "conceito. A validação do rascunho aponta o mesmo problema.",
        )
    rule = next(
        (r for r in content.applicability_rules if r.id == binding.applicability_rule_id), None
    )
    policy = next(
        (p for p in content.evidence_policies if p.id == binding.evidence_policy_id), None
    )
    unit = next((u for u in content.units if u.id == concept.unit_id), None)
    value_set_id = binding.value_set_id or concept.value_set_id
    value_set = next((v for v in content.value_sets if v.id == value_set_id), None)
    cited = {*binding.source_assertion_ids, *concept.source_assertion_ids}
    assertions = [a for a in content.source_assertions if a.id in cited]
    aliases = [
        a
        for a in content.aliases
        if a.target_binding_id == binding.id or a.target_concept_id == concept.id
    ]
    decisions = [
        d for d in content.reconciliation_decisions if binding.id in d.affected_binding_ids
    ]
    codes = tuple(str(v.code) for v in value_set.values) if value_set else ()
    pairs = (
        LiteralPair(
            aspect="nome do campo",
            original=tuple(a.target_literal for a in assertions),
            reconciled=binding.field_name,
        ),
        LiteralPair(
            aspect="conjunto",
            original=tuple(a.set_literal for a in assertions if a.set_literal),
            reconciled=binding.set_name,
        ),
        LiteralPair(
            aspect="tipo",
            original=tuple(a.datatype_literal for a in assertions if a.datatype_literal),
            reconciled=binding.ifc_type or f"(lógico) {concept.logical_type}",
        ),
        LiteralPair(
            aspect="unidade",
            original=tuple(a.unit_literal for a in assertions if a.unit_literal),
            reconciled=None if unit is None else unit.symbol,
        ),
        LiteralPair(
            aspect="domínio",
            original=tuple(a.domain_literal_json for a in assertions if a.domain_literal_json),
            reconciled=json.dumps(list(codes), ensure_ascii=False) if codes else None,
        ),
    )
    notes = tuple(n for n in (concept.notes, binding.notes) if n)
    if binding.carrier_status == "pending_reconciliation":
        notes += ("portador pendente de reconciliação: escrita bloqueada",)
    if binding.scope == "unspecified":
        notes += ("escopo unspecified: não autoriza escrita",)
    return RowDetail(
        row=row,
        concept_definition=tuple(f"[{t.lang}] {t.text}" for t in concept.definition),
        concept_logical_type=concept.logical_type,
        concept_dimension=concept.dimension,
        unit=None if unit is None else f"{unit.symbol} ({unit.dimension})",
        value_set=codes,
        applicability="—"
        if rule is None
        else f"{', '.join(rule.entity_classes)}"
        + (" (com subtipos)" if rule.include_subtypes else " (sem subtipos)"),
        applicability_conditions=()
        if rule is None
        else tuple(f"{c.fact} {c.operator} {list(c.values)}" for c in rule.conditions),
        predefined_types=()
        if rule is None or rule.predefined_types is None
        else rule.predefined_types,
        aliases=tuple(_alias_view(a) for a in aliases),
        policy_id=None if policy is None else policy.id,
        policy_channels=() if policy is None else tuple(policy.admissible_channels),
        policy_on_missing=None if policy is None else policy.on_missing,
        policy_on_conflict=None if policy is None else policy.on_conflict,
        original_vs_reconciled=pairs,
        assertions=tuple(
            AssertionView(
                assertion_id=a.id,
                source_artifact_id=a.source_artifact_id,
                locator=_locator(a),
                target_literal=a.target_literal,
                set_literal=a.set_literal,
                datatype_literal=a.datatype_literal,
                unit_literal=a.unit_literal,
                domain_literal_json=a.domain_literal_json,
                transcription_status=a.transcription_status,
            )
            for a in assertions
        ),
        decisions=tuple(
            DecisionView(
                decision_id=d.id,
                code=d.code,
                status=d.status,
                summary=d.summary,
                justification=d.justification,
            )
            for d in decisions
        ),
        sibling_bindings=tuple(
            sorted(
                b.id for b in content.bindings if b.concept_id == concept.id and b.id != binding.id
            )
        ),
        history=tuple(history),
        notes=notes,
    )


def _value_text(value: Any) -> str:
    if value is None:
        return "—"
    if hasattr(value, "facets") and hasattr(value, "kind"):
        if value.kind == "simple":
            return str(value.text)
        enum = [str(f.value) for f in value.facets if f.name == "enumeration"]
        others = [f"{f.name}={f.value}" for f in value.facets if f.name != "enumeration"]
        return "; ".join([*([f"um de {enum}"] if enum else []), *others]) or str(value.kind)
    if hasattr(value, "model_dump"):
        return json.dumps(value.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    return str(value)


def _analysis_rows(stored: Any) -> list[AnalysisRow]:
    snapshot = stored.snapshot
    expected = {e.requirement.key(): e for e in snapshot.expected_fields}
    evidence: dict[tuple[str, int], Any] = {}
    if stored.enrichment is not None:
        for result in stored.enrichment.results:
            evidence[(result.field.requirement.key(), result.field.element.express_id)] = result
    rows: list[AnalysisRow] = []
    for result in snapshot.requirements:
        field = expected.get(result.requirement.key())
        element = result.element
        element_text = (
            "(sem elemento)"
            if element is None
            else f"{element.ifc_class} #{element.express_id} {element.global_id or ''}".strip()
        )
        requirement = (
            f"{result.requirement.specification_name} · {result.requirement.facet_tag}"
            f"[{result.requirement.index}]"
        )
        expected_text = (
            "—"
            if field is None
            else f"{_value_text(field.set_name)}.{_value_text(field.field_name)} "
            f"tipo={field.data_type or '—'} card={field.cardinality} "
            f"valor={_value_text(field.value)}"
        )
        annotation = result.annotation
        mapping = "não consultado" if annotation is None else annotation.state
        enrichment = (
            None
            if element is None
            else evidence.get((result.requirement.key(), element.express_id))
        )
        if enrichment is None:
            evidence_state, evidence_detail = "não avaliado", None
        else:
            evidence_state = enrichment.status
            proposed = ", ".join(_value_text(a.value) for a in enrichment.alternatives)
            evidence_detail = (
                "; ".join(
                    part
                    for part in (
                        enrichment.reason,
                        f"proposta (requer revisão humana): {proposed}" if proposed else None,
                        None
                        if enrichment.assessment is None
                        else f"avaliação {enrichment.assessment.status}, "
                        f"ação {enrichment.assessment.action}",
                    )
                    if part
                )
                or None
            )
        rows.append(
            AnalysisRow(
                element=element_text,
                requirement=requirement,
                expected=expected_text,
                found=f"IfcTester: {result.backend_detail}"
                if result.backend_detail
                else (result.reason or "—"),
                origin=f"IDS {result.requirement.ids_sha256[:12]}… · "
                f"célula {result.capability_cell}",
                ids_state=result.state,
                ids_reason=result.reason,
                mapping_state=mapping,
                evidence_state=evidence_state,
                evidence_detail=evidence_detail,
            )
        )
    return rows


def as_draft_head(head: DraftHead) -> DraftSummary:
    """Resumo de um ``DraftHead`` devolvido por serviço."""
    return DraftSummary(
        draft_id=head.draft.draft_id,
        title=head.draft.title,
        state=head.draft.state,
        revision=head.revision,
        content_sha256=head.content_sha256,
        base_release=head.draft.base_release,
        candidate_id=head.draft.candidate_id,
        published_release=head.draft.published_release,
    )
