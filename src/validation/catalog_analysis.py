"""Execução durável de uma análise já enfileirada: M2 formal, anexo M1 e M3 (plano §8).

Sequência: carregar o run e conferir a identidade esperada → replay ou leitura do
terminal → claim CAS ``queued → running`` → reabrir fontes, bundle IDS e release
retido (problema de catálogo é lateral) → avaliação IDS real → anexos do catálogo →
enriquecimento M3 com a mesma sessão → conferência antes/depois das fontes →
transação final com snapshot, enriquecimento, cache, eventos e recibo, e CAS
``running → completed/failed``. Nenhuma transação SQLite fica aberta durante a
avaliação.

A exclusão de execução é um lock de arquivo do sistema operacional, separado do
banco: ``OperationalStore.open`` e as unidades de trabalho nunca o tomam, e quem não
o detém continua lendo e enviando comandos. Só o coordenador que detém o lock
recupera runs ``running`` órfãos (``interrupted``) e conclui runs. Token divergente
recusa a conclusão sem gravar nada. Os eventos técnicos usam um contexto ``service``
da instalação, nunca um ator humano. Não instancia pipeline, writer, LLM, bSDD,
registry semântico ou caches legados.
"""

import contextlib
import hashlib
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import IO, Any, Final, Literal, Self, cast

from pydantic import Field, ValidationError, model_validator

from src.artifacts.contracts import ArtifactError, RetainedCatalogRef
from src.artifacts.storage import LocalArtifactStore
from src.domain_catalog.actor import ActorSnapshot, snapshot_actor
from src.domain_catalog.contracts import ContractModel
from src.domain_catalog.curation import utc_now
from src.domain_catalog.draft_store import StoreError
from src.domain_catalog.models import Sha256Hex
from src.domain_catalog.reader import CatalogReader
from src.ifc_analyzer.observations import IfcObservationReader
from src.ifc_analyzer.read_only import IfcSourceError, ReadOnlyIfcSession
from src.operations.actor_context import ActorContextService
from src.operations.command_runner import OperationalRunner, record_ref
from src.operations.contracts import (
    CanonicalUUID,
    OperationalCommand,
    OperationalError,
    OperationalReceipt,
    ResultingRef,
    SchemaVersionOne,
    new_uuid,
)
from src.operations.database import OperationalStore, OperationalUnitOfWork
from src.suggestion_engine.catalog_cache import CatalogCache, cache_components, cache_key
from src.suggestion_engine.catalog_contracts import EnrichmentRun
from src.suggestion_engine.catalog_operations import E3OperationBundle
from src.suggestion_engine.catalog_service import CatalogEnrichmentService
from src.translator.ids_document import IDSGateError, parse_ids_document
from src.validation.analysis_identity import (
    CONDITION_ID,
    AnalysisRun,
    CatalogState,
    ExecutionClaim,
    RunCompletion,
    RunProblem,
    current_execution_profile,
    operation_manifest_sha256,
)
from src.validation.analysis_service import CatalogUnavailable, attach_catalog_annotations
from src.validation.diagnostic_models import DiagnosticSnapshot
from src.validation.ids_engine import EngineError, IdsEngine
from src.validation.schema_bundle import SchemaBundle

LOCK_FILE: Final = "analysis-coordinator.lock"
SYSTEM_ACTOR_KEY: Final = "ifcqc/analysis-executor"
SYSTEM_ACTOR_NAME: Final = "executor local de análises (sistema)"


class CatalogAnalysisRequest(ContractModel):
    """Pedido de execução de um run **já enfileirado**; não carrega identidade editável."""

    schema_version: SchemaVersionOne = 1
    analysis_id: CanonicalUUID
    command_id: CanonicalUUID
    condition_id: Literal["m1-e3-evidence-v1"] = CONDITION_ID
    expected_identity_sha256: Sha256Hex


class CatalogAnalysisReceipt(ContractModel):
    """Recibo de execução concluída: comando, identidade, hashes, estados e problemas."""

    schema_version: SchemaVersionOne = 1
    operational: OperationalReceipt
    analysis_id: CanonicalUUID
    identity_sha256: Sha256Hex
    state: Literal["completed", "failed"]
    snapshot_id: CanonicalUUID | None = None
    diagnostic_sha256: Sha256Hex | None = None
    enrichment_id: CanonicalUUID | None = None
    enrichment_sha256: Sha256Hex | None = None
    catalog_runtime_state: CatalogState | None = None
    field_counts: dict[str, int] = Field(default_factory=dict)
    problems: tuple[RunProblem, ...] = ()

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        """Concluído aponta snapshot e enriquecimento; falho registra problema."""
        produced = (self.snapshot_id, self.diagnostic_sha256, self.enrichment_id)
        if self.state == "completed" and None in produced:
            raise ValueError("execução concluída exige snapshot e enriquecimento")
        if self.state == "failed" and (
            any(item is not None for item in produced) or not self.problems
        ):
            raise ValueError("execução falha não grava resultado e exige problema")
        return self


class PersistedEnrichment(ContractModel):
    """Linha de ``enrichment_runs``: o run M3 com análise e snapshot a que pertence."""

    schema_version: SchemaVersionOne = 1
    enrichment_id: CanonicalUUID
    analysis_id: CanonicalUUID
    snapshot_id: CanonicalUUID
    diagnostic_sha256: Sha256Hex
    run: EnrichmentRun

    @model_validator(mode="after")
    def _owned(self) -> Self:
        """O run M3 é exatamente o desta análise e deste diagnóstico."""
        identity = self.run.identity
        if (identity.enrichment_id, identity.analysis_id, identity.diagnostic_sha256) != (
            self.enrichment_id,
            self.analysis_id,
            self.diagnostic_sha256,
        ):
            raise ValueError("enriquecimento pertence a outra análise ou diagnóstico")
        return self


@dataclass(frozen=True)
class PersistedAnalysis:
    """Run com snapshot, enriquecimento e recibo reabertos e conferidos por hash."""

    run: AnalysisRun
    snapshot: DiagnosticSnapshot | None
    enrichment: EnrichmentRun | None
    receipt: CatalogAnalysisReceipt | None


def execution_arguments(request: CatalogAnalysisRequest) -> dict[str, Any]:
    """Argumentos semânticos do comando ``execute_analysis``."""
    return {
        "analysis_id": str(request.analysis_id),
        "expected_identity_sha256": request.expected_identity_sha256,
        "condition_id": request.condition_id,
    }


def execution_command(
    request: CatalogAnalysisRequest, actor_context_id: uuid.UUID, project_id: uuid.UUID
) -> OperationalCommand:
    """Envelope do comando de execução, com o ator de sistema resolvido."""
    return OperationalCommand.build(
        command_id=request.command_id,
        actor_context_id=actor_context_id,
        operation="execute_analysis",
        project_id=project_id,
        arguments=execution_arguments(request),
    )


def system_actor(store: OperationalStore) -> ActorSnapshot:
    """Contexto ``service`` estável da instalação para os eventos técnicos de execução."""
    context = ActorContextService(store).ensure_system_context(
        key=SYSTEM_ACTOR_KEY, declared_name=SYSTEM_ACTOR_NAME
    )
    return snapshot_actor(context)


# --- lock do coordenador -------------------------------------------------------------


def _try_lock(handle: IO[bytes]) -> bool:
    """Lock exclusivo não bloqueante de região, liberado pelo OS ao fechar/encerrar."""
    handle.seek(0)
    lock: Callable[[], None]
    if sys.platform == "win32":
        import msvcrt

        def lock() -> None:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        def lock() -> None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    try:
        lock()
    except OSError:
        return False
    return True


def _unlock(handle: IO[bytes]) -> None:
    handle.seek(0)
    if sys.platform == "win32":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class AnalysisCoordinator:
    """Exclusão de execução/recuperação por lock de arquivo do OS (não por PID/arquivo)."""

    def __init__(self, root: Path, handle: IO[bytes], token: uuid.UUID) -> None:
        """Use ``AnalysisCoordinator.acquire``."""
        self.root = root
        self.token = token
        self._handle: IO[bytes] | None = handle

    @classmethod
    def acquire(cls, store_root: Path) -> "AnalysisCoordinator":
        """Toma o lock sem esperar; ocupado é ``coordinator_busy`` (não mata ninguém)."""
        root = store_root.resolve()
        try:
            handle = open(root / LOCK_FILE, "a+b")  # noqa: SIM115 - mantido até close()
        except OSError as exc:
            raise OperationalError("store_unavailable", f"lock inacessível: {exc}") from exc
        if not _try_lock(handle):
            handle.close()
            raise OperationalError("coordinator_busy", "outro coordenador detém o lock de execução")
        return cls(root, handle, new_uuid())

    @property
    def held(self) -> bool:
        """O handle com o lock continua aberto neste processo."""
        return self._handle is not None and not self._handle.closed

    def close(self) -> None:
        """Libera o lock (fechar o handle também libera)."""
        handle, self._handle = self._handle, None
        if handle is None or handle.closed:
            return
        with contextlib.suppress(OSError):
            _unlock(handle)
        handle.close()

    def __enter__(self) -> Self:
        """Uso em ``with``; o lock já foi tomado em ``acquire``."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Libera o lock na saída."""
        self.close()

    def require(self, store: OperationalStore) -> None:
        """O lock está detido e pertence à raiz deste banco."""
        if not self.held:
            raise OperationalError("coordinator_busy", "o lock do coordenador não está detido")
        if store.root.resolve() != self.root:
            raise OperationalError("foreign_reference", "coordenador de outro banco operacional")

    def recover_interrupted_runs(
        self, store: OperationalStore, *, clock: Callable[[], str] = utc_now
    ) -> tuple[uuid.UUID, ...]:
        """Marca ``interrupted`` os runs ``running`` órfãos e abandona seus comandos.

        Sob o lock nenhum executor vivo que o respeite detém esses runs; o próprio
        claim deste coordenador nunca é tocado, nem terminal/queued.
        """
        self.require(store)
        actor = system_actor(store)
        recovered: list[uuid.UUID] = []
        with store.transaction() as uow:
            for row in uow.analyses.scan(state="running"):
                run = AnalysisRun.model_validate(row.document)
                claim = run.claim
                assert claim is not None
                if claim.coordinator_token == self.token:
                    continue
                now = clock()
                problem = RunProblem(
                    code="executor_interrupted",
                    message="executor anterior terminou sem concluir; reanalisar cria sucessor",
                )
                interrupted = run.advance(
                    "interrupted", finished_at_utc=now, problems=(*run.problems, problem)
                )
                uow.analyses.replace(
                    str(run.analysis_id), row.row_version, interrupted.model_dump(mode="json")
                )
                command = uow.commands.get(str(claim.command_id))
                if command is not None and command.state == "in_progress":
                    uow.commands.abandon(str(claim.command_id))
                uow.events.append(
                    "operations",
                    {
                        "event": "analysis_interrupted",
                        "analysis_id": str(run.analysis_id),
                        "execution_token": str(claim.execution_token),
                        "command_id": str(claim.command_id),
                        "project_id": str(run.identity.project_id),
                        "actor_context_id": actor.actor_context_id,
                        "at_utc": now,
                    },
                )
                recovered.append(run.analysis_id)
        return tuple(recovered)


# --- execução ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Outcome:
    snapshot: DiagnosticSnapshot | None
    enrichment: EnrichmentRun | None
    problems: tuple[RunProblem, ...]


def _problem(code: str, exc: BaseException) -> RunProblem:
    return RunProblem(code=code, message=str(exc) or type(exc).__name__)


def _event(
    name: str, run: AnalysisRun, command: OperationalCommand, actor: ActorSnapshot, now: str
) -> dict[str, Any]:
    return {
        "event": name,
        "analysis_id": str(run.analysis_id),
        "pair_id": str(run.identity.pair_id),
        "operation": "execute_analysis",
        "command_id": str(command.command_id),
        "project_id": str(run.identity.project_id),
        "actor_context_id": actor.actor_context_id,
        "at_utc": now,
    }


def _persist(
    store: OperationalStore,
    coordinator: AnalysisCoordinator,
    *,
    running: AnalysisRun,
    start_sequence: int,
    command: OperationalCommand,
    actor: ActorSnapshot,
    outcome: _Outcome,
    bundle: E3OperationBundle,
    clock: Callable[[], str],
    new_id: Callable[[], uuid.UUID],
) -> CatalogAnalysisReceipt:
    """Transação final: tudo ou nada, com CAS sobre estado, tokens e versão."""
    analysis_id = str(running.analysis_id)
    with store.transaction() as uow:
        row = uow.analyses.get(analysis_id)
        current = None if row is None else AnalysisRun.model_validate(row.document)
        if (
            not coordinator.held
            or row is None
            or current is None
            or current.state != "running"
            or current.claim != running.claim
            or current.state_version != running.state_version
        ):
            raise OperationalError(
                "execution_claim_conflict",
                f"claim da análise {analysis_id} mudou; resultado não gravado",
                expected=None if running.claim is None else str(running.claim.execution_token),
                actual=None
                if current is None or current.claim is None
                else str(current.claim.execution_token),
            )
        now = clock()
        snapshot, enrichment = outcome.snapshot, outcome.enrichment
        refs = [ResultingRef(kind="analysis", ref_id=running.analysis_id)]
        if snapshot is not None and enrichment is not None:
            uow.diagnostics.insert(snapshot.model_dump(mode="json"))
            stored = PersistedEnrichment(
                enrichment_id=enrichment.identity.enrichment_id,
                analysis_id=running.analysis_id,
                snapshot_id=snapshot.snapshot_id,
                diagnostic_sha256=snapshot.content_sha256,
                run=enrichment,
            )
            uow.enrichments.insert(stored.model_dump(mode="json"))
            contexts = {c.context_sha256: c for c in enrichment.contexts}
            cache = CatalogCache(uow)
            for result in enrichment.results:
                if result.context_sha256 is None:
                    continue
                components = cache_components(snapshot, contexts[result.context_sha256], bundle)
                cache.put(cache_key(components), components, result)
            refs += [
                ResultingRef(kind="diagnostic", ref_id=snapshot.snapshot_id),
                ResultingRef(kind="enrichment", ref_id=enrichment.identity.enrichment_id),
            ]
        state: Literal["completed", "failed"] = "completed" if snapshot is not None else "failed"
        end_event = {
            **_event(f"analysis_{state}", running, command, actor, now),
            "problems": [p.code for p in outcome.problems],
            "field_counts": {} if enrichment is None else enrichment.counts(),
        }
        end_sequence = uow.events.append("operations", end_event)
        operational = OperationalReceipt(
            receipt_id=new_id(),
            command_id=command.command_id,
            operation="execute_analysis",
            status="applied",
            actor_snapshot=actor,
            project_id=running.identity.project_id,
            resulting_refs=tuple(refs),
            event_sequence=(start_sequence, end_sequence),
            committed_at_utc=now,
            payload_sha256=command.payload_sha256,
        )
        receipt = CatalogAnalysisReceipt(
            operational=operational,
            analysis_id=running.analysis_id,
            identity_sha256=running.identity.digest(),
            state=state,
            snapshot_id=None if snapshot is None else snapshot.snapshot_id,
            diagnostic_sha256=None if snapshot is None else snapshot.content_sha256,
            enrichment_id=None if enrichment is None else enrichment.identity.enrichment_id,
            enrichment_sha256=None if enrichment is None else enrichment.content_sha256,
            catalog_runtime_state=None if snapshot is None else snapshot.catalog_runtime_state,
            field_counts={} if enrichment is None else enrichment.counts(),
            problems=outcome.problems,
        )
        completion = RunCompletion(
            snapshot_id=receipt.snapshot_id,
            diagnostic_sha256=receipt.diagnostic_sha256,
            enrichment_id=receipt.enrichment_id,
            enrichment_sha256=receipt.enrichment_sha256,
            command_id=command.command_id,
            receipt_id=operational.receipt_id,
        )
        terminal = current.advance(
            state, finished_at_utc=now, completion=completion, problems=outcome.problems
        )
        uow.analyses.replace(analysis_id, row.row_version, terminal.model_dump(mode="json"))
        uow.commands.complete(
            str(command.command_id),
            {
                "receipt": operational.model_dump(mode="json"),
                "result": receipt.model_dump(mode="json"),
            },
        )
    return receipt


def _stored_receipt(uow: OperationalUnitOfWork, run: AnalysisRun) -> CatalogAnalysisReceipt:
    """Recibo original de um run terminal concluído ou falho."""
    completion = run.completion
    if completion is None:
        raise OperationalError("integrity_error", f"run {run.analysis_id} terminal sem conclusão")
    row = uow.commands.get(str(completion.command_id))
    if row is None or row.state != "completed" or row.receipt is None:
        raise OperationalError("integrity_error", "comando de execução do run sem recibo")
    try:
        receipt = CatalogAnalysisReceipt.model_validate(row.receipt["result"])
    except (KeyError, ValidationError) as exc:
        raise OperationalError("integrity_error", "recibo de execução gravado inválido") from exc
    if (receipt.analysis_id, receipt.operational.receipt_id) != (
        run.analysis_id,
        completion.receipt_id,
    ):
        raise OperationalError("integrity_error", "recibo gravado de outra execução")
    return receipt


class CatalogAnalysisExecutor:
    """Executa runs enfileirados com componentes concretos e bundle de operações explícito."""

    def __init__(
        self,
        store: OperationalStore,
        artifacts: LocalArtifactStore,
        operation_bundle: E3OperationBundle,
        *,
        clock: Callable[[], str] = utc_now,
        new_id: Callable[[], uuid.UUID] = new_uuid,
    ) -> None:
        """Autoridade comum, artefatos retidos e bundle da condição."""
        self._store = store
        self._artifacts = artifacts
        self._bundle = operation_bundle
        self._clock = clock
        self._new_id = new_id
        self._actor: ActorSnapshot | None = None

    def _system_actor(self) -> ActorSnapshot:
        if self._actor is None:
            self._actor = system_actor(self._store)
        return self._actor

    def _prepare(
        self, request: CatalogAnalysisRequest
    ) -> tuple[AnalysisRun, OperationalCommand, ActorSnapshot]:
        with self._store.transaction() as uow:
            row = uow.analyses.get(str(request.analysis_id))
        if row is None:
            raise OperationalError("not_found", f"análise {request.analysis_id} não existe")
        run = AnalysisRun.model_validate(row.document)
        if request.condition_id != run.identity.condition_id:
            raise OperationalError("analysis_identity_mismatch", "condição difere da do run")
        digest = run.identity.digest()
        if digest != request.expected_identity_sha256:
            raise OperationalError(
                "analysis_identity_mismatch",
                "identidade do run difere da esperada",
                expected=request.expected_identity_sha256,
                actual=digest,
            )
        actor = self._system_actor()
        command = execution_command(
            request, uuid.UUID(actor.actor_context_id), run.identity.project_id
        )
        return run, command, actor

    @staticmethod
    def _answer(
        uow: OperationalUnitOfWork, command: OperationalCommand, run: AnalysisRun
    ) -> CatalogAnalysisReceipt | None:
        """Replay da chave, ou leitura do run que já não está ``queued``."""
        found = OperationalRunner.replay(uow, command)
        if found is not None:
            try:
                return CatalogAnalysisReceipt.model_validate(found.result)
            except ValidationError as exc:
                raise OperationalError("integrity_error", "recibo de execução inválido") from exc
        if run.state == "running":
            raise OperationalError("analysis_in_progress", f"análise {run.analysis_id} em curso")
        if run.state == "interrupted":
            raise OperationalError(
                "analysis_interrupted", f"análise {run.analysis_id} interrompida; reanalise"
            )
        if run.state in ("completed", "failed"):
            return _stored_receipt(uow, run)
        return None

    def lookup(self, request: CatalogAnalysisRequest) -> CatalogAnalysisReceipt | None:
        """Resposta sem executar e sem lock: replay, terminal ou ``None`` se enfileirado."""
        run, command, _ = self._prepare(request)
        with self._store.transaction() as uow:
            current = uow.analyses.get(str(run.analysis_id))
            assert current is not None
            return self._answer(uow, command, AnalysisRun.model_validate(current.document))

    def execute(
        self, request: CatalogAnalysisRequest, coordinator: AnalysisCoordinator
    ) -> CatalogAnalysisReceipt:
        """Claim, avaliação fora de transação e conclusão atômica sob o lock detido."""
        coordinator.require(self._store)
        run, command, actor = self._prepare(request)
        profile = current_execution_profile(run.identity.limits)
        if (profile.verifier, profile.condition_config_sha256) != (
            run.identity.verifier,
            run.identity.condition_config_sha256,
        ):
            raise OperationalError(
                "execution_profile_mismatch",
                "runtime atual não cumpre o verificador/condição congelados no run",
                expected=run.identity.condition_config_sha256,
                actual=profile.condition_config_sha256,
            )
        canonical = operation_manifest_sha256()
        if self._bundle.manifest_sha256 != canonical:
            # O bundle executado tem de ser o congelado na condição (E3-05).
            raise OperationalError(
                "execution_profile_mismatch",
                "bundle de operações difere do da condição",
                expected=canonical,
                actual=self._bundle.manifest_sha256,
            )
        schema_bundle = SchemaBundle.load()
        with self._store.transaction() as uow:
            row = uow.analyses.get(str(run.analysis_id))
            assert row is not None
            queued = AnalysisRun.model_validate(row.document)
            answered = self._answer(uow, command, queued)
            if answered is not None:
                return answered
            uow.commands.reserve(
                command_id=str(command.command_id),
                namespace="operations",
                operation="execute_analysis",
                payload_sha256=command.payload_sha256,
                actor_context_id=str(command.actor_context_id),
                record_ref=record_ref("execute_analysis", command.command_id),
            )
            now = self._clock()
            claim = ExecutionClaim(
                execution_token=self._new_id(),
                coordinator_token=coordinator.token,
                command_id=command.command_id,
                claimed_at_utc=now,
            )
            running = queued.advance("running", claim=claim, started_at_utc=now)
            uow.analyses.replace(
                str(run.analysis_id), row.row_version, running.model_dump(mode="json")
            )
            start = uow.events.append(
                "operations",
                {
                    **_event("analysis_started", running, command, actor, now),
                    "execution_token": str(claim.execution_token),
                },
            )
        outcome = self._evaluate(running, schema_bundle)
        return _persist(
            self._store,
            coordinator,
            running=running,
            start_sequence=start,
            command=command,
            actor=actor,
            outcome=outcome,
            bundle=self._bundle,
            clock=self._clock,
            new_id=self._new_id,
        )

    def _open_catalog(self, run: AnalysisRun) -> CatalogReader | CatalogUnavailable:
        identity = run.identity
        ref = identity.catalog_ref
        if identity.catalog_state != "available" or ref is None:
            frozen = cast(Literal["not_attached", "invalid", "unavailable"], identity.catalog_state)
            return CatalogUnavailable(
                state=frozen, reason=f"catálogo {frozen} ao enfileirar", catalog=ref
            )
        with self._store.transaction() as uow:
            row = uow.releases.get(ref.catalog_id, ref.version)
        if row is None:
            return CatalogUnavailable(state="invalid", reason="release sem registro", catalog=ref)
        retained = RetainedCatalogRef.model_validate(row.document["retained"])
        if retained.catalog != ref:
            return CatalogUnavailable(
                state="invalid", reason="registro de outro release", catalog=ref
            )
        try:
            reader = self._artifacts.open_retained_catalog(retained, registry=self._bundle.registry)
        except ArtifactError as exc:
            state: Literal["invalid", "unavailable"] = (
                "unavailable" if exc.reason == "artifact_unavailable" else "invalid"
            )
            return CatalogUnavailable(state=state, reason=str(exc), catalog=ref)
        return reader

    def _evaluate(self, run: AnalysisRun, schema_bundle: SchemaBundle) -> _Outcome:
        """Avaliação formal e M3 sobre as fontes retidas; nada é gravado aqui."""
        identity = run.identity
        limits = identity.limits
        try:
            ifc_path = self._artifacts.read_verified_source(identity.ifc)
            ids_data = self._artifacts.read_verified_source(identity.ids).read_bytes()
            if hashlib.sha256(ids_data).hexdigest() != identity.ids.sha256:
                raise ArtifactError("artifact_integrity_error", "IDS mudou durante a leitura")
            session = ReadOnlyIfcSession.open(
                identity.ifc,
                ifc_path,
                max_bytes=limits.max_ifc_bytes,
                max_entities=limits.max_ifc_entities,
            )
            document = parse_ids_document(
                ids_data,
                schema_bundle,
                max_bytes=limits.max_ids_bytes,
                max_depth=limits.max_xml_depth,
                max_nodes=limits.max_xml_nodes,
            )
            formal = IdsEngine(schema_bundle).evaluate(
                session, document, identity, clock=self._clock, snapshot_id=self._new_id()
            )
            catalog = self._open_catalog(run)
            problems: list[RunProblem] = []
            if isinstance(catalog, CatalogUnavailable) and catalog.state != "not_attached":
                problems.append(
                    RunProblem(
                        code=f"catalog_{catalog.state}",
                        message=catalog.reason or f"catálogo {catalog.state}",
                    )
                )
            snapshot = attach_catalog_annotations(formal, catalog)
            enrichment = CatalogEnrichmentService(self._bundle).enrich(
                snapshot,
                observations=IfcObservationReader(
                    session,
                    identity.analysis_id,
                    max_observations=limits.max_observations_per_field,
                ),
                catalog=catalog,
                enrichment_id=self._new_id(),
            )
            problems += [
                RunProblem(code=f"enrichment_{p.code}", message=p.message)
                for p in enrichment.problems
            ]
            session.verify_unchanged()
            # Os dois artefatos da identidade são reconferidos ao concluir (A14, E3-11).
            self._artifacts.read_verified_source(identity.ifc)
            self._artifacts.read_verified_source(identity.ids)
        except (ArtifactError, IfcSourceError, IDSGateError, EngineError) as exc:
            return _Outcome(None, None, (_problem(exc.reason, exc),))
        except StoreError as exc:
            return _Outcome(None, None, (_problem("store_error", exc),))
        except Exception as exc:  # falha inesperada do run: registrada, nunca sucesso
            return _Outcome(None, None, (_problem("internal_error", exc),))
        return _Outcome(snapshot, enrichment, tuple(problems))


def execute_catalog_analysis(
    request: CatalogAnalysisRequest,
    *,
    store: OperationalStore,
    artifacts: LocalArtifactStore,
    operation_bundle: E3OperationBundle,
) -> CatalogAnalysisReceipt:
    """Responde por replay/terminal sem lock; senão toma o lock, recupera e executa."""
    executor = CatalogAnalysisExecutor(store, artifacts, operation_bundle)
    answered = executor.lookup(request)
    if answered is not None:
        return answered
    with AnalysisCoordinator.acquire(store.root) as coordinator:
        coordinator.recover_interrupted_runs(store)
        return executor.execute(request, coordinator)


# --- leitura do histórico --------------------------------------------------------------


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise OperationalError("integrity_error", message)


def load_analysis(store: OperationalStore, analysis_id: uuid.UUID) -> PersistedAnalysis:
    """Run e resultados reabertos, com hashes e posse conferidos; adulteração é erro."""
    with store.transaction() as uow:
        row = uow.analyses.get(str(analysis_id))
        if row is None:
            raise OperationalError("not_found", f"análise {analysis_id} não existe")
        try:
            run = AnalysisRun.model_validate(row.document)
            completion = run.completion
            if completion is None or run.state not in ("completed", "failed"):
                return PersistedAnalysis(run=run, snapshot=None, enrichment=None, receipt=None)
            receipt = _stored_receipt(uow, run)
            snapshot = enrichment = None
            if completion.snapshot_id is not None:
                found = uow.diagnostics.get(str(completion.snapshot_id))
                _check(found is not None, "snapshot da conclusão ausente")
                assert found is not None
                snapshot = DiagnosticSnapshot.model_validate(found.document)
                _check(snapshot.snapshot_id == completion.snapshot_id, "snapshot de outra chave")
                _check(snapshot.identity == run.identity, "snapshot de outra análise")
                _check(
                    snapshot.content_sha256 == completion.diagnostic_sha256,
                    "hash do snapshot difere da conclusão",
                )
            if completion.enrichment_id is not None:
                found = uow.enrichments.get(str(completion.enrichment_id))
                _check(found is not None and snapshot is not None, "enriquecimento ausente")
                assert found is not None
                assert snapshot is not None
                stored = PersistedEnrichment.model_validate(found.document)
                _check(
                    (stored.enrichment_id, stored.analysis_id, stored.snapshot_id)
                    == (completion.enrichment_id, run.analysis_id, snapshot.snapshot_id),
                    "enriquecimento de outra análise",
                )
                _check(
                    stored.diagnostic_sha256 == snapshot.content_sha256
                    and stored.run.content_sha256 == completion.enrichment_sha256,
                    "hash do enriquecimento difere da conclusão",
                )
                enrichment = stored.run
            _check(
                (receipt.diagnostic_sha256, receipt.enrichment_sha256)
                == (completion.diagnostic_sha256, completion.enrichment_sha256),
                "recibo difere da conclusão",
            )
        except (ValidationError, StoreError, KeyError) as exc:
            raise OperationalError("integrity_error", f"análise {analysis_id}: {exc}") from exc
    return PersistedAnalysis(run=run, snapshot=snapshot, enrichment=enrichment, receipt=receipt)
