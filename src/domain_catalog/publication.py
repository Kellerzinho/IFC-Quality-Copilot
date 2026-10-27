"""Candidato e publicação de release do catálogo (E2, M1-09; parte do M1-16).

Fluxo que falha com segurança (plano M1 §7.2; plano M6 §7.2):

1. **Candidato** (``prepare_release``): da revisão aprovada, materializa o conteúdo
   (propostas → ``approved``), monta os bytes canônicos, grava numa área de preparo
   isolada, reabre pelo leitor da E1 (hashes, layout, conteúdo) e só então registra o
   candidato com sua identidade exata (catálogo, versão e SHA-256 do manifesto).
2. **Intenção** (``publish``, fase A): numa transação, confere os portões — candidato
   exato, aprovação ainda vigente, release-base ainda o último publicado, versão livre,
   nenhuma outra publicação em andamento no catálogo, pessoa com responsável declarado
   e justificativa, pendências — e grava a intenção. A intenção registrada **reserva a
   linha do catálogo** até ser concluída ou abandonada (plano M6 §7.1). Rascunho e
   candidato ficam travados em ``publishing``.
3. **Promoção** (fase B, fora do banco): confere de novo os portões de conclusão,
   promove o preparo para o destino final por renomeação exclusiva (nunca sobrescreve)
   e reabre os bytes promovidos.
4. **Recibo** (fase C): na mesma transação, confere mais uma vez os portões de
   conclusão e grava o recibo de publicação, eventos e o comando concluído. O release
   só está disponível a partir daqui; pasta sem recibo não é release.

A intenção conserva a identidade do que foi decidido, não congela a validade da base:
base superada na conclusão é ``BaseSupersededError`` e exige reconciliação explícita
(abandonar e refazer o rascunho), com os bytes preservados. Falha depois da intenção
deixa ``PublicationIncompleteError`` com a intenção identificada: nada fica
disponível, e a retomada (mesmo comando, ou ``resume_publication``) ou o abandono
(``abandon_publication``) são explícitos. A recuperação confere intenção, bytes e
portões; nunca inventa aprovação por achar uma pasta. Publicar não adota o release em
projeto nenhum e não altera releases anteriores.

Não há armazenamento operacional: ``ReleaseArtifactStore`` é a porta para o M6, e só
existe o adaptador de teste, que se declara não operacional nos recibos.
"""

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Literal, NamedTuple, Protocol

from pydantic import Field

from src.domain_catalog.actor import ActorContextResolver, ActorSnapshot
from src.domain_catalog.content import CatalogContent
from src.domain_catalog.contracts import CatalogReleaseRef, ContractModel, SemVer
from src.domain_catalog.curation import (
    CommandRunner,
    CommandScope,
    Subject,
    evolve,
    new_local_id,
    payload_sha256,
    revision_key,
    utc_now,
    validated_input,
)
from src.domain_catalog.curation_errors import (
    BaseSupersededError,
    CandidateMismatchError,
    ContentHashMismatchError,
    CurationError,
    CurationNotFoundError,
    IdempotencyConflictError,
    InvalidTransitionError,
    PublicationGateError,
    PublicationIncompleteError,
    PublicationInProgressError,
    RevisionConflictError,
    ValidationGateError,
)
from src.domain_catalog.curation_models import (
    ChangeRequest,
    CommandMeta,
    CommandOutcome,
    CommandRecord,
    CommitReceipt,
    DiffSummary,
    DraftRecord,
    DraftRevision,
    PendingItem,
    PositiveInt,
    PublicationIntent,
    PublicationReceipt,
    ReleaseCandidate,
    ReviewRecord,
    ValidationSummary,
)
from src.domain_catalog.curation_models import (
    content_sha256 as hash_content,
)
from src.domain_catalog.curation_validation import (
    PENDING_CARRIER_POLICY,
    content_diff,
    materialize_release_content,
    pending_items,
    validate_revision,
)
from src.domain_catalog.draft_store import (
    CurationStore,
    CurationTransaction,
    StoreError,
    insert_model,
    read_model,
    replace_model,
    require_model,
    scan_models,
)
from src.domain_catalog.errors import CatalogPackageError, CatalogValidationError
from src.domain_catalog.models import LocalId, NonEmptyText, Sha256Hex
from src.domain_catalog.operations import DEFAULT_OPERATION_REGISTRY, OperationRegistry
from src.domain_catalog.package import (
    ComponentTerms,
    ContentOrigin,
    PackageLimits,
    ReleaseFiles,
    build_release_files,
)
from src.domain_catalog.reader import CatalogReader, open_catalog


class ArtifactStoreError(CurationError):
    """Falha do armazenamento de releases (preparo, promoção, quarentena, inventário).

    ``phase`` identifica a etapa e ``errno`` a causa do sistema operacional, quando
    houver; a exceção original fica encadeada em ``__cause__``. Não é sucesso parcial:
    pasta sem recibo não é release, e nada do que falhou é apagado.
    """

    code = "artifact_store"

    def __init__(self, message: str, *, phase: str | None = None, errno: int | None = None) -> None:
        """Guarda a etapa e o ``errno`` (se a causa for do sistema operacional)."""
        self.phase = phase
        self.errno = errno
        super().__init__(message)


class ReleaseCollisionError(ArtifactStoreError):
    """Destino final já ocupado; nada é sobrescrito."""

    code = "release_collision"


def storage_failure(phase: str, exc: OSError) -> ArtifactStoreError:
    """``OSError`` do armazenamento como erro tipado da etapa, sem o caminho completo.

    A mensagem cita só o último componente do caminho; o caminho e o erro original
    continuam disponíveis em ``__cause__`` para o diagnóstico técnico.
    """
    where = f" ({Path(str(exc.filename)).name})" if exc.filename else ""
    reason = exc.strerror or type(exc).__name__
    return ArtifactStoreError(
        f"falha do armazenamento de releases na etapa {phase}{where}: {reason}",
        phase=phase,
        errno=exc.errno,
    )


@contextmanager
def _storage_phase(phase: str) -> Iterator[None]:
    """Converte ``OSError`` cru vindo do armazenamento em ``ArtifactStoreError`` da etapa."""
    try:
        yield
    except OSError as exc:
        raise storage_failure(phase, exc) from exc


class StoreInventory(NamedTuple):
    """Entradas presentes nas áreas de preparo e de releases, publicadas ou não."""

    staged: tuple[Path, ...]
    releases: tuple[Path, ...]


class ReleaseArtifactStore(Protocol):
    """Bytes imutáveis de candidatos e releases (porta para o armazenamento do M6).

    Obrigação de erro: toda falha de armazenamento sai como ``ArtifactStoreError``
    (ou subclasse), com ``phase`` e ``errno`` quando a causa é do sistema operacional e
    a exceção original em ``__cause__``; nunca ``OSError`` cru (``storage_failure``
    monta o erro). Falha não apaga nem move o que encontrou no caminho. O serviço
    normaliza de novo, por defesa, o que um adaptador deixar escapar.
    """

    @property
    def operational(self) -> bool:
        """Se é o armazenamento operacional; adaptador de teste diz ``False``."""
        ...

    def stage(self, candidate_id: str, release: ReleaseFiles) -> Path:
        """Grava o candidato numa pasta de preparo nova e devolve o caminho."""
        ...

    def staging_path(self, candidate_id: str) -> Path:
        """Local da pasta de preparo do candidato (pode não existir)."""
        ...

    def release_path(self, ref: CatalogReleaseRef) -> Path:
        """Destino final do release (pode não existir)."""
        ...

    def promote(self, candidate_id: str, ref: CatalogReleaseRef) -> Path:
        """Promove o preparo ao destino final; destino ocupado é ``ReleaseCollisionError``."""
        ...

    def quarantine(self, path: Path, label: str) -> Path:
        """Move uma pasta para a quarentena, sem apagar."""
        ...

    def inventory(self) -> StoreInventory:
        """Entradas presentes no preparo e na área de releases, inclusive soltas."""
        ...


class IntentInspection(ContractModel):
    """Situação em disco de uma publicação interrompida, sem alterar nada."""

    intent_id: LocalId
    candidate_id: LocalId
    release: CatalogReleaseRef
    recorded_at: str
    staged: bool
    staged_valid: bool
    promoted: bool
    promoted_valid: bool


class ResidualStagingInspection(ContractModel):
    """Preparo remanescente de candidato publicado ou invalidado, preservado no disco."""

    candidate_id: LocalId
    state: Literal["published", "invalidated"]
    path: str


class PublicationInspection(ContractModel):
    """Relatório somente leitura, sem atomicidade entre o snapshot do banco e o disco.

    Resíduos conhecidos não são órfãos nem autorização para apagar ou republicar.
    Sob alteração concorrente, a visão pode ser transitória; inspecionar novamente
    depois da operação não substitui os portões da publicação.
    """

    pending_intents: tuple[IntentInspection, ...] = ()
    unregistered_releases: tuple[str, ...] = ()
    orphan_staging: tuple[str, ...] = ()
    residual_staging: tuple[ResidualStagingInspection, ...] = ()
    damaged_publications: tuple[str, ...] = ()
    artifact_store_operational: bool


class _PrepareInput(ContractModel):
    draft_id: LocalId
    revision: PositiveInt
    content_sha256: Sha256Hex
    version: SemVer
    terms: tuple[ComponentTerms, ...] = Field(min_length=1)
    reason: NonEmptyText


class _PublishInput(ContractModel):
    candidate_id: LocalId
    version: SemVer
    manifest_sha256: Sha256Hex
    justification: NonEmptyText
    acknowledged_pending: tuple[NonEmptyText, ...] = ()


class _IntentActionInput(ContractModel):
    intent_id: LocalId
    reason: NonEmptyText


class _Completion(NamedTuple):
    """Registros conferidos pelos portões de conclusão, com as versões para a troca."""

    intent: PublicationIntent
    intent_version: int
    candidate: ReleaseCandidate
    candidate_version: int
    draft: DraftRecord
    draft_version: int
    approval: ReviewRecord


class _Plan(NamedTuple):
    """Candidato montado em memória, antes de gravar o preparo."""

    draft: DraftRecord
    revision: DraftRevision
    approval: ReviewRecord
    files: ReleaseFiles
    released: CatalogContent
    origin: ContentOrigin
    created_at: str
    validation_summary: ValidationSummary
    pending: tuple[PendingItem, ...]
    diff: DiffSummary


def _semver(version: str) -> tuple[int, int, int]:
    major, minor, patch = (int(part) for part in version.split("."))
    return major, minor, patch


def publication_key(catalog_id: str, version: str) -> str:
    """Chave única do recibo: um catálogo não publica duas vezes a mesma versão."""
    return f"{catalog_id}#{version}"


def content_origin_of(content: CatalogContent) -> ContentOrigin:
    """Conteúdo com qualquer fonte sintética é ``synthetic_fixture``, nunca curado."""
    synthetic = any(a.artifact_type == "synthetic_fixture" for a in content.source_artifacts)
    return "synthetic_fixture" if synthetic else "curated"


_PACKAGE_FAILURES = (CatalogPackageError, CatalogValidationError, ArtifactStoreError, OSError)


class PublicationService:
    """Candidatos, publicação e releases publicados sobre as portas do M6.

    Também atende ``PublishedReleases``: só um release com recibo é publicado; uma
    pasta sem recibo não é aberta como release.
    """

    def __init__(
        self,
        store: CurationStore,
        actors: ActorContextResolver,
        artifacts: ReleaseArtifactStore,
        *,
        registry: OperationRegistry = DEFAULT_OPERATION_REGISTRY,
        clock: Callable[[], str] = utc_now,
        new_id: Callable[[], str] = new_local_id,
        limits: PackageLimits | None = None,
    ) -> None:
        """Portas de persistência, ator e armazenamento de releases."""
        self._runner = CommandRunner(store, actors, clock, new_id)
        self._store = store
        self._artifacts = artifacts
        self._registry = registry
        self._limits = limits

    # --- releases publicados -------------------------------------------------------------

    def list_published(self, catalog_id: str | None = None) -> tuple[PublicationReceipt, ...]:
        """Recibos de publicação, em ordem de versão."""
        with self._store.transaction() as tx:
            receipts = [r for r, _ in scan_models(tx, "publication", PublicationReceipt)]
        return tuple(
            sorted(
                (r for r in receipts if catalog_id is None or r.release.catalog_id == catalog_id),
                key=lambda r: (r.release.catalog_id, _semver(r.release.version)),
            )
        )

    def latest_published(self, catalog_id: str) -> CatalogReleaseRef | None:
        """Último release publicado do catálogo; ``None`` se ainda não há."""
        published = self.list_published(catalog_id)
        return published[-1].release if published else None

    def get_publication(self, ref: CatalogReleaseRef) -> PublicationReceipt:
        """Recibo do release com essa referência exata (ID, versão e hash)."""
        with self._store.transaction() as tx:
            found = read_model(
                tx, "publication", publication_key(ref.catalog_id, ref.version), PublicationReceipt
            )
        if found is None or found[0].release != ref:
            raise CurationNotFoundError(f"release {ref.version} com esse hash não foi publicado")
        return found[0]

    def open_published(self, ref: CatalogReleaseRef) -> CatalogReader:
        """Reader do release publicado; sem recibo não abre, e pacote ruim não vira vazio."""
        self.get_publication(ref)
        return open_catalog(
            ref, self._artifacts.release_path(ref), limits=self._limits, registry=self._registry
        )

    def get_candidate(self, candidate_id: str) -> ReleaseCandidate:
        """Candidato pelo ID."""
        with self._store.transaction() as tx:
            return require_model(tx, "candidate", candidate_id, ReleaseCandidate, "candidato")[0]

    def get_intent(self, intent_id: str) -> PublicationIntent:
        """Intenção de publicação pelo ID."""
        with self._store.transaction() as tx:
            return require_model(tx, "intent", intent_id, PublicationIntent, "intenção")[0]

    # --- candidato ---------------------------------------------------------------------

    def prepare_release(
        self,
        command: CommandMeta,
        *,
        draft_id: str,
        revision: int,
        content_sha256: str,
        version: str,
        terms: Sequence[ComponentTerms],
        reason: str,
    ) -> CommandOutcome[ReleaseCandidate]:
        """Monta, grava em preparo e reabre o candidato da revisão aprovada; não publica."""
        data = validated_input(
            _PrepareInput,
            draft_id=draft_id,
            revision=revision,
            content_sha256=content_sha256,
            version=version,
            terms=tuple(terms),
            reason=reason,
        )
        payload = data.model_dump(mode="json")
        replayed = self._runner.lookup(command, "prepare_release", payload, ReleaseCandidate)
        if replayed is not None:
            return replayed
        self._runner.authorized_actor(command, "prepare_release")
        plan = self._plan(data)
        candidate_id = self._runner.new_id()
        with _storage_phase("stage"):
            staged = self._artifacts.stage(candidate_id, plan.files)
        open_catalog(plan.files.ref, staged, limits=self._limits, registry=self._registry)

        def body(scope: CommandScope) -> tuple[ReleaseCandidate, Subject]:
            draft, version_number, current, approval = self._candidate_gates(scope.tx, data)
            if current.content_sha256 != plan.revision.content_sha256:
                raise ContentHashMismatchError("a revisão mudou durante a preparação")
            candidate = ReleaseCandidate(
                candidate_id=candidate_id,
                draft_id=draft.draft_id,
                revision=current.revision,
                content_sha256=current.content_sha256,
                approval_id=approval.review_id,
                release=plan.files.ref,
                previous_release=draft.base_release,
                content_origin=plan.origin,
                manifest_created_at=plan.created_at,
                terms=data.terms,
                release_content_sha256=hash_content(plan.released),
                validation=plan.validation_summary,
                pending_items=plan.pending,
                diff=plan.diff,
                state="prepared",
                prepared_by=scope.actor,
                prepared_at=scope.now,
                command_id=scope.command_id,
            )
            insert_model(scope.tx, "candidate", candidate_id, candidate)
            replace_model(
                scope.tx,
                "draft",
                draft.draft_id,
                version_number,
                evolve(draft, candidate_id=candidate_id, updated_at=scope.now),
            )
            scope.emit(
                "candidate",
                candidate_id,
                from_state=None,
                to_state="prepared",
                revision=current.revision,
                reason=data.reason,
                details={
                    "draft_id": draft.draft_id,
                    "version": candidate.release.version,
                    "manifest_sha256": candidate.release.manifest_sha256,
                    "content_origin": candidate.content_origin,
                },
            )
            return candidate, Subject("candidate", candidate_id, current.revision)

        return self._runner.execute(command, "prepare_release", payload, ReleaseCandidate, body)

    def _candidate_gates(
        self, tx: CurationTransaction, data: _PrepareInput
    ) -> tuple[DraftRecord, int, DraftRevision, ReviewRecord]:
        """Rascunho aprovado na revisão exata, sem candidato ativo, base e versão válidas."""
        draft, version = require_model(tx, "draft", data.draft_id, DraftRecord, "rascunho")
        if draft.state != "approved" or draft.approval_id is None:
            raise InvalidTransitionError(
                f"rascunho em {draft.state}: candidato exige revisão aprovada e vigente"
            )
        if data.revision != draft.current_revision:
            raise RevisionConflictError(
                f"a revisão aprovada é {draft.current_revision}, não {data.revision}",
                expected=data.revision,
                current=draft.current_revision,
            )
        current = require_model(
            tx, "revision", revision_key(draft.draft_id, data.revision), DraftRevision, "revisão"
        )[0]
        if current.content_sha256 != data.content_sha256:
            raise ContentHashMismatchError(
                f"hash informado não é o da revisão aprovada ({current.content_sha256})"
            )
        approval = require_model(tx, "review", draft.approval_id, ReviewRecord, "aprovação")[0]
        if (approval.verdict, approval.revision, approval.content_sha256) != (
            "approve",
            current.revision,
            current.content_sha256,
        ):
            raise PublicationGateError("a aprovação vigente não corresponde à revisão exata")
        if draft.candidate_id is not None:
            active = read_model(tx, "candidate", draft.candidate_id, ReleaseCandidate)
            if active is not None and active[0].state in ("prepared", "publishing"):
                raise InvalidTransitionError(
                    f"rascunho já tem candidato {active[0].state}: {draft.candidate_id}"
                )
        self._check_base_and_version(tx, draft.base_release, draft.catalog.catalog_id, data.version)
        return draft, version, current, approval

    def _check_base_and_version(
        self,
        tx: CurationTransaction,
        base: CatalogReleaseRef | None,
        catalog_id: str,
        version: str,
        *,
        remedy: str = "refaça o rascunho a partir do release atual",
    ) -> None:
        """Base precisa ser o último publicado; a versão cresce e não se repete."""
        published = sorted(
            (r for r, _ in scan_models(tx, "publication", PublicationReceipt)),
            key=lambda r: _semver(r.release.version),
        )
        mine = [r for r in published if r.release.catalog_id == catalog_id]
        latest = mine[-1].release if mine else None
        if latest != base:
            raise BaseSupersededError(
                f"release-base desatualizado: o rascunho parte de "
                f"{None if base is None else base.version}, o último publicado é "
                f"{None if latest is None else latest.version}; {remedy}"
            )
        if any(r.release.version == version for r in mine):
            raise PublicationGateError(f"versão {version} já publicada neste catálogo")
        if base is not None and _semver(version) <= _semver(base.version):
            raise PublicationGateError(
                f"versão {version} precisa ser maior que a do release-base {base.version}"
            )

    def _plan(self, data: _PrepareInput) -> _Plan:
        """Confere os portões, valida e monta os bytes do candidato, sem gravar nada."""
        with self._store.transaction() as tx:
            draft, _, current, approval = self._candidate_gates(tx, data)
        base = None if draft.base_release is None else self.open_published(draft.base_release)
        base_content = None if base is None else base.content
        report = validate_revision(
            draft_id=draft.draft_id,
            revision=current.revision,
            content=current.content,
            base=base_content,
            base_release=draft.base_release,
            registry=self._registry,
            pending_carrier_policy=PENDING_CARRIER_POLICY,
        )
        if not report.passed:
            codes = ", ".join(sorted({x.code for x in report.by_severity("error")}))
            raise ValidationGateError(f"candidato recusado: validação com erro ({codes})")
        released = materialize_release_content(current.content)
        origin = content_origin_of(released)
        created_at = self._runner.clock()
        files = build_release_files(
            released,
            catalog=draft.catalog,
            version=data.version,
            created_at=created_at,
            content_origin=origin,
            terms=data.terms,
            previous_release=draft.base_release,
        )
        return _Plan(
            draft=draft,
            revision=current,
            approval=approval,
            files=files,
            released=released,
            origin=origin,
            created_at=created_at,
            validation_summary=report.summary(),
            pending=pending_items(released),
            diff=content_diff(base_content, released),
        )

    # --- publicação ---------------------------------------------------------------------

    def publish(
        self,
        command: CommandMeta,
        *,
        candidate_id: str,
        version: str,
        manifest_sha256: str,
        justification: str,
        acknowledged_pending: Sequence[str] = (),
    ) -> CommandOutcome[PublicationReceipt]:
        """Publica o candidato exato; repetir o mesmo comando devolve ou retoma.

        Exige ação humana com responsável declarado, justificativa, versão e hash
        exatos do candidato, aprovação ainda vigente e release-base ainda atual. Só o
        recibo torna o release disponível; nenhum projeto o adota automaticamente.
        """
        data = validated_input(
            _PublishInput,
            candidate_id=candidate_id,
            version=version,
            manifest_sha256=manifest_sha256,
            justification=justification,
            acknowledged_pending=tuple(acknowledged_pending),
        )
        payload = data.model_dump(mode="json")
        digest = payload_sha256("publish", command.actor_context_id, payload)
        actor = self._runner.authorized_actor(command, "publish")
        intent, replayed = self._record_intent(command, data, digest, actor)
        if replayed is not None:
            return replayed
        return self._finish(intent, actor, completion=None)

    def resume_publication(
        self, command: CommandMeta, *, intent_id: str, reason: str
    ) -> CommandOutcome[PublicationReceipt]:
        """Conclui publicação interrompida, conferindo intenção, bytes e portões."""
        data = validated_input(_IntentActionInput, intent_id=intent_id, reason=reason)
        payload = data.model_dump(mode="json")
        replayed = self._runner.lookup(command, "resume_publication", payload, PublicationReceipt)
        if replayed is not None:
            return replayed
        actor = self._runner.authorized_actor(command, "resume_publication")
        intent = self.get_intent(data.intent_id)
        if intent.state != "recorded":
            raise InvalidTransitionError(f"intenção em {intent.state} não pode ser retomada")
        digest = payload_sha256("resume_publication", command.actor_context_id, payload)
        return self._finish(intent, actor, completion=(command, digest, data.reason))

    def abandon_publication(
        self, command: CommandMeta, *, intent_id: str, reason: str
    ) -> CommandOutcome[PublicationIntent]:
        """Abandona publicação interrompida; release promovido sem recibo vai à quarentena.

        A decisão é gravada **antes** de tocar no disco: o candidato volta a ``prepared``
        e o rascunho a ``approved``, e a retomada concorrente passa a ser recusada. Só
        depois a pasta promovida sem recibo vai para a quarentena, e somente se nenhum
        recibo nem outra intenção em andamento a reivindicar. Se mover a pasta falhar, o
        abandono continua gravado e repetir o mesmo comando tenta de novo. Nada foi
        publicado; uma nova publicação exige novo comando.
        """
        data = validated_input(_IntentActionInput, intent_id=intent_id, reason=reason)
        payload = data.model_dump(mode="json")
        replayed = self._runner.lookup(command, "abandon_publication", payload, PublicationIntent)
        if replayed is not None:
            self._quarantine_unclaimed(replayed.value.release)
            return replayed
        self._runner.authorized_actor(command, "abandon_publication")

        def body(scope: CommandScope) -> tuple[PublicationIntent, Subject]:
            current, version = require_model(
                scope.tx, "intent", data.intent_id, PublicationIntent, "intenção"
            )
            if current.state != "recorded":
                raise InvalidTransitionError(f"intenção em {current.state} não pode ser abandonada")
            closed = evolve(
                current, state="abandoned", closed_at=scope.now, closing_reason=data.reason
            )
            replace_model(scope.tx, "intent", current.intent_id, version, closed)
            candidate, candidate_version = require_model(
                scope.tx, "candidate", current.candidate_id, ReleaseCandidate, "candidato"
            )
            replace_model(
                scope.tx,
                "candidate",
                candidate.candidate_id,
                candidate_version,
                evolve(candidate, state="prepared"),
            )
            draft, draft_version = require_model(
                scope.tx, "draft", candidate.draft_id, DraftRecord, "rascunho"
            )
            replace_model(
                scope.tx,
                "draft",
                draft.draft_id,
                draft_version,
                evolve(draft, state="approved", updated_at=scope.now),
            )
            original = require_model(
                scope.tx, "command", current.command_id, CommandRecord, "comando"
            )
            replace_model(
                scope.tx,
                "command",
                current.command_id,
                original[1],
                evolve(original[0], state="abandoned"),
            )
            scope.emit(
                "intent",
                current.intent_id,
                from_state="recorded",
                to_state="abandoned",
                reason=data.reason,
            )
            scope.emit(
                "candidate",
                candidate.candidate_id,
                from_state="publishing",
                to_state="prepared",
                reason=data.reason,
            )
            scope.emit(
                "draft",
                draft.draft_id,
                from_state="publishing",
                to_state="approved",
                reason=data.reason,
            )
            return closed, Subject("intent", current.intent_id)

        outcome = self._runner.execute(
            command, "abandon_publication", payload, PublicationIntent, body
        )
        self._quarantine_unclaimed(outcome.value.release)
        return outcome

    def _quarantine_unclaimed(self, ref: CatalogReleaseRef) -> None:
        """Põe na quarentena a pasta final que nenhum recibo nem intenção ativa reivindica."""
        with _storage_phase("quarantine"):
            final = self._artifacts.release_path(ref)
            present = final.exists()
        if present and not self._is_claimed(ref):
            with _storage_phase("quarantine"):
                self._artifacts.quarantine(final, f"sem-recibo-{ref.version}")

    def _is_claimed(self, ref: CatalogReleaseRef) -> bool:
        """Se há recibo da versão ou intenção ainda registrada para ela (outra tentativa)."""
        with self._store.transaction() as tx:
            if tx.get("publication", publication_key(ref.catalog_id, ref.version)) is not None:
                return True
            return any(
                intent.state == "recorded"
                and (intent.release.catalog_id, intent.release.version)
                == (ref.catalog_id, ref.version)
                for intent, _ in scan_models(tx, "intent", PublicationIntent)
            )

    def _record_intent(
        self, command: CommandMeta, data: _PublishInput, digest: str, actor: ActorSnapshot
    ) -> tuple[PublicationIntent, CommandOutcome[PublicationReceipt] | None]:
        """Fase A: portões e intenção durável, ou a retomada/repetição do mesmo comando."""
        with self._store.transaction() as tx:
            found = read_model(tx, "command", command.command_id, CommandRecord)
            if found is not None:
                record = found[0]
                if (record.operation, record.payload_sha256, record.actor_context_id) != (
                    "publish",
                    digest,
                    command.actor_context_id,
                ):
                    raise IdempotencyConflictError(
                        f"chave {command.command_id} já usada por outro comando"
                    )
                if record.state == "abandoned":
                    raise InvalidTransitionError(
                        f"publicação {command.command_id} foi abandonada; use um comando novo"
                    )
                if record.state == "completed" and record.receipt and record.result:
                    return self.get_intent_in(tx, record.intent_id), CommandOutcome(
                        receipt=record.receipt,
                        value=PublicationReceipt.model_validate(record.result),
                        replayed=True,
                    )
                return self.get_intent_in(tx, record.intent_id), None
            now = self._runner.clock()
            scope = CommandScope(tx, actor, now, command.command_id, "publish", self._runner.new_id)
            candidate, candidate_version, draft, draft_version = self._publish_gates(tx, data)
            intent_id = scope.new_id()
            scope.emit(
                "intent",
                intent_id,
                from_state=None,
                to_state="recorded",
                reason=data.justification,
                details={
                    "candidate_id": candidate.candidate_id,
                    "version": candidate.release.version,
                    "manifest_sha256": candidate.release.manifest_sha256,
                },
            )
            scope.emit(
                "candidate",
                candidate.candidate_id,
                from_state="prepared",
                to_state="publishing",
                reason=data.justification,
            )
            scope.emit(
                "draft",
                draft.draft_id,
                from_state="approved",
                to_state="publishing",
                reason=data.justification,
            )
            intent = PublicationIntent(
                intent_id=intent_id,
                candidate_id=candidate.candidate_id,
                release=candidate.release,
                command_id=command.command_id,
                publisher=actor,
                justification=data.justification,
                acknowledged_pending=tuple(sorted(set(data.acknowledged_pending))),
                recorded_at=now,
                recorded_event_seqs=tuple(scope.event_seqs),
                state="recorded",
            )
            insert_model(tx, "intent", intent_id, intent)
            replace_model(
                tx,
                "candidate",
                candidate.candidate_id,
                candidate_version,
                evolve(candidate, state="publishing"),
            )
            replace_model(
                tx,
                "draft",
                draft.draft_id,
                draft_version,
                evolve(draft, state="publishing", updated_at=now),
            )
            insert_model(
                tx,
                "command",
                command.command_id,
                CommandRecord(
                    command_id=command.command_id,
                    operation="publish",
                    payload_sha256=digest,
                    actor_context_id=command.actor_context_id,
                    state="in_progress",
                    recorded_at=now,
                    intent_id=intent_id,
                ),
            )
        return intent, None

    @staticmethod
    def get_intent_in(tx: CurationTransaction, intent_id: str | None) -> PublicationIntent:
        """Intenção dentro de uma transação aberta."""
        if intent_id is None:
            raise CurationNotFoundError("comando de publicação sem intenção registrada")
        return require_model(tx, "intent", intent_id, PublicationIntent, "intenção")[0]

    def _publish_gates(
        self, tx: CurationTransaction, data: _PublishInput
    ) -> tuple[ReleaseCandidate, int, DraftRecord, int]:
        """Candidato exato, aprovação vigente, base atual, versão livre e pendências."""
        candidate, candidate_version = require_model(
            tx, "candidate", data.candidate_id, ReleaseCandidate, "candidato"
        )
        if candidate.state != "prepared":
            raise InvalidTransitionError(f"candidato em {candidate.state} não pode ser publicado")
        if (data.version, data.manifest_sha256) != (
            candidate.release.version,
            candidate.release.manifest_sha256,
        ):
            raise CandidateMismatchError(
                f"versão/hash informados ({data.version}, {data.manifest_sha256[:12]}…) não são "
                f"os do candidato ({candidate.release.version}, "
                f"{candidate.release.manifest_sha256[:12]}…)"
            )
        draft, draft_version = require_model(
            tx, "draft", candidate.draft_id, DraftRecord, "rascunho"
        )
        if (draft.state, draft.approval_id, draft.current_revision, draft.candidate_id) != (
            "approved",
            candidate.approval_id,
            candidate.revision,
            candidate.candidate_id,
        ):
            raise PublicationGateError(
                "a aprovação que sustenta o candidato não está mais vigente; reaprove e "
                "prepare novo candidato"
            )
        self._check_base_and_version(
            tx, candidate.previous_release, candidate.release.catalog_id, candidate.release.version
        )
        self._check_catalog_line_free(tx, candidate)
        expected = sorted(item.entity_id for item in candidate.pending_items)
        given = sorted(set(data.acknowledged_pending))
        if given and given != expected:
            raise PublicationGateError(
                f"reconhecimento não corresponde às pendências do candidato: {expected}"
            )
        if PENDING_CARRIER_POLICY == "acknowledge" and expected and given != expected:
            raise PublicationGateError(
                f"publicação com pendências exige reconhecimento explícito de: {expected}"
            )
        return candidate, candidate_version, draft, draft_version

    def _check_catalog_line_free(
        self, tx: CurationTransaction, candidate: ReleaseCandidate
    ) -> None:
        """Reserva da linha: uma publicação em andamento por catálogo (plano M6 §7.1).

        A intenção registrada é a reserva e vale até ser concluída ou abandonada. A
        conferência ocorre na mesma transação que grava a nova intenção; a porta de
        persistência garante transações serializáveis, então duas intenções do mesmo
        catálogo nunca ficam registradas ao mesmo tempo.
        """
        catalog_id = candidate.release.catalog_id
        for intent, _ in scan_models(tx, "intent", PublicationIntent):
            if intent.state == "recorded" and intent.release.catalog_id == catalog_id:
                raise PublicationInProgressError(
                    f"catálogo já tem publicação em andamento (intenção {intent.intent_id}, "
                    f"versão {intent.release.version}): retome-a (resume_publication) ou "
                    "abandone-a (abandon_publication) antes de publicar outra"
                )

    def _completion_gates(self, tx: CurationTransaction, intent_id: str) -> _Completion:
        """Pré-condições para concluir a intenção, conferidas antes de promover e no recibo.

        A intenção conserva a identidade do que foi decidido, não congela a validade da
        base. Exige intenção ainda registrada; candidato e rascunho travados em
        ``publishing`` sobre a aprovação exata (número e hash da revisão); release-base
        ainda o último publicado; versão livre e maior que a do base.
        """
        intent, intent_version = require_model(
            tx, "intent", intent_id, PublicationIntent, "intenção"
        )
        if intent.state != "recorded":
            raise InvalidTransitionError(f"intenção em {intent.state}: nada a concluir")
        candidate, candidate_version = require_model(
            tx, "candidate", intent.candidate_id, ReleaseCandidate, "candidato"
        )
        draft, draft_version = require_model(
            tx, "draft", candidate.draft_id, DraftRecord, "rascunho"
        )
        if (candidate.state, draft.state) != ("publishing", "publishing"):
            raise InvalidTransitionError("candidato ou rascunho fora de publishing")
        approval = require_model(tx, "review", candidate.approval_id, ReviewRecord, "aprovação")[0]
        locked = (draft.approval_id, draft.current_revision, draft.candidate_id) == (
            candidate.approval_id,
            candidate.revision,
            candidate.candidate_id,
        )
        exact = (approval.verdict, approval.revision, approval.content_sha256) == (
            "approve",
            candidate.revision,
            candidate.content_sha256,
        )
        if not (locked and exact):
            raise PublicationGateError(
                "a aprovação que sustenta o candidato não é mais a aprovação exata da revisão; "
                "nada é publicado"
            )
        self._check_base_and_version(
            tx,
            candidate.previous_release,
            candidate.release.catalog_id,
            candidate.release.version,
            remedy=(
                f"a intenção {intent_id} não pode ser concluída: abandone-a "
                "(abandon_publication) e refaça o rascunho a partir do release atual"
            ),
        )
        return _Completion(
            intent, intent_version, candidate, candidate_version, draft, draft_version, approval
        )

    def _finish(
        self,
        intent: PublicationIntent,
        actor: ActorSnapshot,
        completion: tuple[CommandMeta, str, str] | None,
    ) -> CommandOutcome[PublicationReceipt]:
        """Fases B e C: confere, promove e verifica os bytes; grava o recibo.

        Os portões de conclusão são conferidos antes de promover e de novo na transação
        do recibo. Falha não publica.
        """
        with self._store.transaction() as tx:
            candidate = self._completion_gates(tx, intent.intent_id).candidate
        final = self._promote_verified(candidate, intent.intent_id)
        try:
            return self._record_publication(intent.intent_id, actor, final, completion)
        except StoreError as exc:
            raise PublicationIncompleteError(
                f"release promovido e verificado, mas o recibo não foi gravado: {exc}",
                intent_id=intent.intent_id,
                phase="receipt",
            ) from exc

    def _opens(self, ref: CatalogReleaseRef, path: Path) -> bool:
        try:
            open_catalog(ref, path, limits=self._limits, registry=self._registry)
        except CatalogPackageError:
            return False
        return True

    def _promote_verified(self, candidate: ReleaseCandidate, intent_id: str) -> Path:
        """Destino final com exatamente os bytes do candidato; nunca sobrescreve outra pasta.

        Destino já ocupado só é aceito se abrir com a referência exata do candidato
        (retomada depois de promoção); preparo ausente ou alterado é posto em quarentena
        e refeito da revisão aprovada, conferindo o mesmo hash.
        """
        ref = candidate.release
        phase = "verify_existing"
        try:
            final = self._artifacts.release_path(ref)
            if final.exists():
                open_catalog(ref, final, limits=self._limits, registry=self._registry)
                return final
            phase = "check_staging"
            staged = self._artifacts.staging_path(candidate.candidate_id)
            if not (staged.is_dir() and self._opens(ref, staged)):
                phase = "rebuild_staging"
                if staged.exists():
                    self._artifacts.quarantine(staged, f"stg-{ref.version}")
                staged = self._artifacts.stage(candidate.candidate_id, self._rebuild(candidate))
                open_catalog(ref, staged, limits=self._limits, registry=self._registry)
            phase = "promote"
            promoted = self._artifacts.promote(candidate.candidate_id, ref)
            phase = "verify_promoted"
            open_catalog(ref, promoted, limits=self._limits, registry=self._registry)
        except _PACKAGE_FAILURES as exc:
            raise PublicationIncompleteError(
                f"publicação interrompida na fase {phase}: {exc}; nada foi disponibilizado",
                intent_id=intent_id,
                phase=phase,
            ) from exc
        return promoted

    def _rebuild(self, candidate: ReleaseCandidate) -> ReleaseFiles:
        """Refaz os bytes do candidato a partir da revisão aprovada; precisa dar o mesmo hash."""
        with self._store.transaction() as tx:
            draft = require_model(tx, "draft", candidate.draft_id, DraftRecord, "rascunho")[0]
            revision = require_model(
                tx,
                "revision",
                revision_key(candidate.draft_id, candidate.revision),
                DraftRevision,
                "revisão",
            )[0]
        files = build_release_files(
            materialize_release_content(revision.content),
            catalog=draft.catalog,
            version=candidate.release.version,
            created_at=candidate.manifest_created_at,
            content_origin=candidate.content_origin,
            terms=candidate.terms,
            previous_release=candidate.previous_release,
        )
        if files.ref != candidate.release:
            raise ArtifactStoreError("a reconstrução não reproduz os bytes do candidato")
        return files

    def _record_publication(
        self,
        intent_id: str,
        actor: ActorSnapshot,
        final: Path,
        completion: tuple[CommandMeta, str, str] | None,
    ) -> CommandOutcome[PublicationReceipt]:
        """Fase C: portões de conclusão, recibo, estados, eventos e comandos numa transação."""
        with self._store.transaction() as tx:
            now = self._runner.clock()
            gates = self._completion_gates(tx, intent_id)
            current, intent_version = gates.intent, gates.intent_version
            candidate, candidate_version = gates.candidate, gates.candidate_version
            draft, draft_version = gates.draft, gates.draft_version
            approval = gates.approval
            command_id = completion[0].command_id if completion else current.command_id
            operation = "resume_publication" if completion else "publish"
            scope = CommandScope(tx, actor, now, command_id, operation, self._runner.new_id)
            receipt = PublicationReceipt(
                receipt_id=scope.new_id(),
                release=candidate.release,
                previous_release=candidate.previous_release,
                candidate_id=candidate.candidate_id,
                intent_id=current.intent_id,
                draft_id=candidate.draft_id,
                revision=candidate.revision,
                content_sha256=candidate.content_sha256,
                release_content_sha256=candidate.release_content_sha256,
                approval_id=approval.review_id,
                approved_by=approval.reviewer,
                approval_justification=approval.justification,
                published_by=current.publisher,
                publication_justification=current.justification,
                completed_by=actor,
                acknowledged_pending=current.acknowledged_pending,
                validation=candidate.validation,
                pending_items=candidate.pending_items,
                content_origin=candidate.content_origin,
                published_at=now,
                command_id=current.command_id,
                store_operational=self._store.operational,
                artifact_store_operational=self._artifacts.operational,
            )
            key = publication_key(candidate.release.catalog_id, candidate.release.version)
            insert_model(tx, "publication", key, receipt)
            replace_model(
                tx,
                "intent",
                current.intent_id,
                intent_version,
                evolve(current, state="completed", closed_at=now),
            )
            replace_model(
                tx,
                "candidate",
                candidate.candidate_id,
                candidate_version,
                evolve(candidate, state="published"),
            )
            replace_model(
                tx,
                "draft",
                draft.draft_id,
                draft_version,
                evolve(
                    draft,
                    state="published",
                    published_release=candidate.release,
                    updated_at=now,
                ),
            )
            scope.emit(
                "publication",
                receipt.receipt_id,
                from_state=None,
                to_state="published",
                revision=candidate.revision,
                reason=current.justification,
                details={
                    "version": candidate.release.version,
                    "manifest_sha256": candidate.release.manifest_sha256,
                    "location": str(final),
                },
            )
            scope.emit(
                "intent",
                current.intent_id,
                from_state="recorded",
                to_state="completed",
                reason=None if completion is None else completion[2],
            )
            scope.emit(
                "candidate", candidate.candidate_id, from_state="publishing", to_state="published"
            )
            scope.emit("draft", draft.draft_id, from_state="publishing", to_state="published")
            for request, request_version in scan_models(tx, "request", ChangeRequest):
                if request.draft_id == draft.draft_id and request.state == "approved":
                    replace_model(
                        tx,
                        "request",
                        request.request_id,
                        request_version,
                        evolve(request, published_release=candidate.release),
                    )
                    scope.emit(
                        "request",
                        request.request_id,
                        from_state="approved",
                        to_state="approved",
                        details={"published_version": candidate.release.version},
                    )
            publish_receipt = CommitReceipt(
                command_id=current.command_id,
                operation="publish",
                subject_kind="publication",
                subject_id=receipt.receipt_id,
                revision=candidate.revision,
                event_seqs=(*current.recorded_event_seqs, *scope.event_seqs),
                committed_at=now,
                store_operational=self._store.operational,
            )
            original, original_version = require_model(
                tx, "command", current.command_id, CommandRecord, "comando"
            )
            replace_model(
                tx,
                "command",
                current.command_id,
                original_version,
                evolve(
                    original,
                    state="completed",
                    receipt=publish_receipt,
                    result=receipt.model_dump(mode="json"),
                ),
            )
            if completion is None:
                return CommandOutcome(receipt=publish_receipt, value=receipt, replayed=False)
            resume_meta, digest, _ = completion
            resume_receipt = CommitReceipt(
                command_id=resume_meta.command_id,
                operation="resume_publication",
                subject_kind="publication",
                subject_id=receipt.receipt_id,
                revision=candidate.revision,
                event_seqs=tuple(scope.event_seqs),
                committed_at=now,
                store_operational=self._store.operational,
            )
            insert_model(
                tx,
                "command",
                resume_meta.command_id,
                CommandRecord(
                    command_id=resume_meta.command_id,
                    operation="resume_publication",
                    payload_sha256=digest,
                    actor_context_id=resume_meta.actor_context_id,
                    state="completed",
                    recorded_at=now,
                    receipt=resume_receipt,
                    result=receipt.model_dump(mode="json"),
                    intent_id=current.intent_id,
                ),
            )
            return CommandOutcome(receipt=resume_receipt, value=receipt, replayed=False)

    # --- reconciliação -------------------------------------------------------------------

    def inspect(self) -> PublicationInspection:
        """Relatório somente leitura do que está incompleto, solto ou danificado."""
        with self._store.transaction() as tx:
            intents = [i for i, _ in scan_models(tx, "intent", PublicationIntent)]
            candidates = [c for c, _ in scan_models(tx, "candidate", ReleaseCandidate)]
            receipts = [r for r, _ in scan_models(tx, "publication", PublicationReceipt)]
        with _storage_phase("inspect"):
            return self._inspect_storage(intents, candidates, receipts)

    def _inspect_storage(
        self,
        intents: list[PublicationIntent],
        candidates: list[ReleaseCandidate],
        receipts: list[PublicationReceipt],
    ) -> PublicationInspection:
        """Confronta os registros com o que está nas áreas de preparo e de releases."""
        recorded = [intent for intent in intents if intent.state == "recorded"]
        pending: list[IntentInspection] = []
        for intent in recorded:
            staged = self._artifacts.staging_path(intent.candidate_id)
            final = self._artifacts.release_path(intent.release)
            pending.append(
                IntentInspection(
                    intent_id=intent.intent_id,
                    candidate_id=intent.candidate_id,
                    release=intent.release,
                    recorded_at=intent.recorded_at,
                    staged=staged.exists(),
                    staged_valid=staged.exists() and self._opens(intent.release, staged),
                    promoted=final.exists(),
                    promoted_valid=final.exists() and self._opens(intent.release, final),
                )
            )
        inventory = self._artifacts.inventory()
        known_releases = {self._artifacts.release_path(r.release) for r in receipts} | {
            self._artifacts.release_path(i.release) for i in recorded
        }
        known_staging = {
            self._artifacts.staging_path(candidate.candidate_id): candidate
            for candidate in candidates
        }
        unregistered = tuple(str(path) for path in inventory.releases if path not in known_releases)
        orphans = tuple(str(path) for path in inventory.staged if path not in known_staging)
        residuals: list[ResidualStagingInspection] = []
        for path in inventory.staged:
            candidate = known_staging.get(path)
            if candidate is not None and candidate.state in ("published", "invalidated"):
                residuals.append(
                    ResidualStagingInspection(
                        candidate_id=candidate.candidate_id,
                        state=candidate.state,
                        path=str(path),
                    )
                )
        damaged = tuple(
            f"{r.release.catalog_id} {r.release.version}"
            for r in receipts
            if not self._opens(r.release, self._artifacts.release_path(r.release))
        )
        return PublicationInspection(
            pending_intents=tuple(pending),
            unregistered_releases=unregistered,
            orphan_staging=orphans,
            residual_staging=tuple(residuals),
            damaged_publications=damaged,
            artifact_store_operational=self._artifacts.operational,
        )
