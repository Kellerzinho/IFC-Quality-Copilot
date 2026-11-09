"""Fila de análises por par IFC–IDS com identidade congelada no enfileiramento (§2.1, §8).

Toda análise nasce ``queued`` com ``AnalysisIdentity`` completa: fontes exatas do par,
pin e proveniência exatos quando o projeto tem pin (nunca omitidos em silêncio),
verificador/condição/limites do perfil que o runtime cumpre. O estado do catálogo
retido é diagnosticado antes de congelar: ausente vira ``unavailable`` e adulterado
``invalid``, conservando ref/pin/proveniência esperados. O pai é a análise anterior
do mesmo par (ordem de inserção). Enfileirar não executa nada.
"""

import uuid
from collections.abc import Callable
from typing import Any

from src.artifacts.contracts import ArtifactError, RetainedCatalogRef
from src.artifacts.storage import LocalArtifactStore
from src.domain_catalog.actor import ActorSnapshot
from src.domain_catalog.contracts import ContractModel
from src.domain_catalog.curation import utc_now
from src.operations.command_runner import Effect, OperationalRunner
from src.operations.contracts import (
    CanonicalUUID,
    NonNegativeInt,
    OperationalCommand,
    OperationalError,
    OperationalReceipt,
    ResultingRef,
    SchemaVersionOne,
    new_uuid,
)
from src.operations.database import OperationalStore, OperationalUnitOfWork
from src.operations.project_models import ModelPairBinding, ProjectCatalogPin, ProjectRecord
from src.validation.analysis_identity import (
    AnalysisIdentity,
    AnalysisRun,
    CatalogState,
    ExecutionProfile,
    current_execution_profile,
)


class AnalysisQueueReceipt(ContractModel):
    """Recibo de enfileiramento: comando, projeto, pin vigente e análises novas."""

    schema_version: SchemaVersionOne = 1
    operational: OperationalReceipt
    project_id: CanonicalUUID
    pin_revision: NonNegativeInt
    queued_analysis_ids: tuple[CanonicalUUID, ...]


def require_profile(profile: ExecutionProfile) -> None:
    """O perfil pedido precisa ser exatamente o que este runtime cumpre."""
    current = current_execution_profile(profile.limits)
    if profile != current:
        raise OperationalError(
            "execution_profile_mismatch",
            "perfil de execução difere do runtime atual",
            expected=profile.condition_config_sha256,
            actual=current.condition_config_sha256,
        )


def load_pin(uow: OperationalUnitOfWork, project_id: uuid.UUID) -> ProjectCatalogPin | None:
    """Pin corrente do projeto, ou ``None``."""
    head = uow.pins.get_head(str(project_id))
    if head is None:
        return None
    row = uow.pins.get_revision(str(project_id), head.document["pin_revision"])
    if row is None:
        raise OperationalError("integrity_error", "head de pin sem revisão")
    return ProjectCatalogPin.model_validate(row.document)


def load_project(uow: OperationalUnitOfWork, project_id: uuid.UUID) -> tuple[ProjectRecord, int]:
    """Head do projeto e sua versão de linha."""
    row = uow.projects.get(str(project_id))
    if row is None:
        raise OperationalError("not_found", f"projeto {project_id} não existe")
    return ProjectRecord.model_validate(row.document), row.row_version


def retained_release(uow: OperationalUnitOfWork, pin: ProjectCatalogPin) -> RetainedCatalogRef:
    """Release retido do pin (registro da autoridade, nunca caminho livre)."""
    row = uow.releases.get(pin.catalog.catalog_id, pin.catalog.version)
    if row is None:
        raise OperationalError("integrity_error", "pin sem release retido registrado")
    retained = RetainedCatalogRef.model_validate(row.document["retained"])
    if retained.catalog != pin.catalog:
        raise OperationalError("integrity_error", "release retido difere do pin")
    return retained


def diagnose_catalog(
    artifacts: LocalArtifactStore, retained: RetainedCatalogRef | None
) -> CatalogState:
    """Estado do catálogo retido no momento de congelar a identidade."""
    if retained is None:
        return "not_attached"
    try:
        artifacts.open_retained_catalog(retained)
    except ArtifactError as exc:
        return "unavailable" if exc.reason == "artifact_unavailable" else "invalid"
    return "available"


def parent_of(uow: OperationalUnitOfWork, pair_id: uuid.UUID) -> uuid.UUID | None:
    """Análise anterior do mesmo par (mais recentemente enfileirada), se houver."""
    row = uow.analyses.latest(pair_id=str(pair_id))
    return None if row is None else uuid.UUID(row.document["analysis_id"])


def new_run(
    *,
    analysis_id: uuid.UUID,
    pair: ModelPairBinding,
    pin: ProjectCatalogPin | None,
    catalog_state: CatalogState,
    profile: ExecutionProfile,
    actor: ActorSnapshot,
    reason: str,
    now: str,
    parent: uuid.UUID | None,
) -> AnalysisRun:
    """Run ``queued`` com identidade completa e congelada."""
    attached = pin is not None and catalog_state != "not_attached"
    identity = AnalysisIdentity(
        project_id=pair.project_id,
        analysis_id=analysis_id,
        pair_id=pair.pair_id,
        pair_revision=pair.pair_revision,
        ifc=pair.ifc,
        ids=pair.ids,
        catalog_ref=pin.catalog if attached and pin else None,
        pin_revision=pin.pin_revision if attached and pin else None,
        catalog_provenance=pin.catalog_provenance if attached and pin else None,
        catalog_state=catalog_state,
        verifier=profile.verifier,
        condition_config_sha256=profile.condition_config_sha256,
        limits=profile.limits,
    )
    return AnalysisRun(
        analysis_id=analysis_id,
        identity=identity,
        state="queued",
        state_version=1,
        parent_analysis_id=parent,
        queued_by=actor,
        queue_reason=reason,
        queued_at_utc=now,
    )


def queued_event(run: AnalysisRun) -> dict[str, Any]:
    """Evento operacional de enfileiramento."""
    return {
        "event": "analysis_queued",
        "analysis_id": str(run.analysis_id),
        "pair_id": str(run.identity.pair_id),
        "pair_revision": run.identity.pair_revision,
        "pin_revision": run.identity.pin_revision,
        "catalog_state": run.identity.catalog_state,
        "parent_analysis_id": None
        if run.parent_analysis_id is None
        else str(run.parent_analysis_id),
    }


def initial_analysis_arguments(
    *,
    project_id: uuid.UUID,
    pair_id: uuid.UUID,
    expected_pair_revision: int,
    expected_pair_set_revision: int,
    execution_profile: ExecutionProfile,
) -> dict[str, Any]:
    """Argumentos de ``queue_initial_analysis``."""
    return {
        "project_id": str(project_id),
        "pair_id": str(pair_id),
        "expected_pair_revision": expected_pair_revision,
        "expected_pair_set_revision": expected_pair_set_revision,
        "execution_profile": execution_profile.model_dump(mode="json"),
    }


def initial_analysis_command(
    command_id: uuid.UUID,
    actor: uuid.UUID,
    project_id: uuid.UUID,
    pair_id: uuid.UUID,
    expected_pair_revision: int,
    expected_pair_set_revision: int,
    execution_profile: ExecutionProfile,
) -> OperationalCommand:
    """Envelope de ``queue_initial_analysis``."""
    return OperationalCommand.build(
        command_id=command_id,
        actor_context_id=actor,
        operation="queue_initial_analysis",
        project_id=project_id,
        arguments=initial_analysis_arguments(
            project_id=project_id,
            pair_id=pair_id,
            expected_pair_revision=expected_pair_revision,
            expected_pair_set_revision=expected_pair_set_revision,
            execution_profile=execution_profile,
        ),
    )


class AnalysisQueueService:
    """Enfileiramento explícito de análise de um par e consultas de runs."""

    def __init__(
        self,
        store: OperationalStore,
        artifacts: LocalArtifactStore,
        *,
        clock: Callable[[], str] = utc_now,
        new_id: Callable[[], uuid.UUID] = new_uuid,
    ) -> None:
        """Autoridade comum e artefatos retidos."""
        self._store = store
        self._artifacts = artifacts
        self._runner = OperationalRunner(store, clock=clock, new_id=new_id)
        self._new_id = new_id

    def queue_initial_analysis(
        self,
        *,
        command: OperationalCommand,
        project_id: uuid.UUID,
        pair_id: uuid.UUID,
        expected_pair_revision: int,
        expected_pair_set_revision: int,
        execution_profile: ExecutionProfile,
    ) -> AnalysisQueueReceipt:
        """Primeira análise de um par: sem catálogo, ou com o pin exato do projeto."""
        arguments = initial_analysis_arguments(
            project_id=project_id,
            pair_id=pair_id,
            expected_pair_revision=expected_pair_revision,
            expected_pair_set_revision=expected_pair_set_revision,
            execution_profile=execution_profile,
        )
        self._runner.verify_envelope(
            command, operation="queue_initial_analysis", project_id=project_id, arguments=arguments
        )
        found = self._runner.lookup(command)
        if found is not None:
            return AnalysisQueueReceipt.model_validate(found.result)
        require_profile(execution_profile)
        with self._store.transaction() as uow:
            pin = load_pin(uow, project_id)
            retained = None if pin is None else retained_release(uow, pin)
        catalog_state = diagnose_catalog(self._artifacts, retained)

        def body(uow: OperationalUnitOfWork, actor: ActorSnapshot, now: str) -> Effect:
            project, _ = load_project(uow, project_id)
            if project.pair_set_revision != expected_pair_set_revision:
                raise OperationalError(
                    "stale_pair_set",
                    "conjunto de pares mudou",
                    expected=expected_pair_set_revision,
                    actual=project.pair_set_revision,
                )
            current = next((p for p in project.active_pair_refs if p.pair_id == pair_id), None)
            if current is None:
                raise OperationalError("not_found", f"par ativo {pair_id} não existe no projeto")
            if current.pair_revision != expected_pair_revision:
                raise OperationalError(
                    "stale_pair",
                    "par mudou",
                    expected=expected_pair_revision,
                    actual=current.pair_revision,
                )
            current_pin = load_pin(uow, project_id)
            if current_pin != pin:
                raise OperationalError("stale_pin", "pin mudou durante o enfileiramento")
            run = new_run(
                analysis_id=self._new_id(),
                pair=current,
                pin=pin,
                catalog_state=catalog_state,
                profile=execution_profile,
                actor=actor,
                reason="primeira análise do par",
                now=now,
                parent=parent_of(uow, pair_id),
            )
            uow.analyses.insert(run.model_dump(mode="json"))

            def finalize(receipt: OperationalReceipt) -> AnalysisQueueReceipt:
                return AnalysisQueueReceipt(
                    operational=receipt,
                    project_id=project_id,
                    pin_revision=0 if pin is None else pin.pin_revision,
                    queued_analysis_ids=(run.analysis_id,),
                )

            return Effect(
                "applied",
                (ResultingRef(kind="analysis", ref_id=run.analysis_id),),
                (queued_event(run),),
                finalize=finalize,
            )

        outcome = self._runner.run(
            command,
            operation="queue_initial_analysis",
            project_id=project_id,
            arguments=arguments,
            requirement="human_or_service",
            body=body,
        )
        return AnalysisQueueReceipt.model_validate(outcome.result)

    def load_run(self, analysis_id: uuid.UUID) -> AnalysisRun:
        """Run pela identidade; ausência é ``not_found``."""
        with self._store.transaction() as uow:
            row = uow.analyses.get(str(analysis_id))
        if row is None:
            raise OperationalError("not_found", f"análise {analysis_id} não existe")
        return AnalysisRun.model_validate(row.document)

    def list_runs(self, project_id: uuid.UUID) -> list[AnalysisRun]:
        """Runs do projeto em ordem de enfileiramento."""
        with self._store.transaction() as uow:
            rows = uow.analyses.scan_inserted(project_id=str(project_id))
        return [AnalysisRun.model_validate(row.document) for row in rows]
