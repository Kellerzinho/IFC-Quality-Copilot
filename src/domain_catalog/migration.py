"""Planejar, confirmar e adotar release de catálogo num projeto (E3.2b, M1-11; plano §4).

``prepare_catalog_adoption`` retém e reabre o alvo, confere a proveniência pela cadeia
E2 histórica exata na mesma autoridade (recibo, candidato, intenção, revisão,
aprovação, validação e atores), recusa colisão versão/hash também contra o histórico
retido, congela os pares ativos e o perfil, calcula o diff E3.2a contra o pin
corrente (ou declara ``no_previous_catalog``) e persiste o plano imutável.
``apply_catalog_adoption`` recebe só ID e hash confirmados: replay primeiro, depois
hash, perfil, artefatos (alvo e release anterior do plano reabertos), cadeia e CAS de
pin (revisão e referência)/pares/plano numa transação que grava pin,
análises ``queued``, eventos, comando e recibo — ou nada. Referência corrente com nova
chave é ``noop`` auditado. Rollback cria pin e análises novos; nada de A1 é reativado.
Resultado IDS ou falha de execução posterior não desfaz uma adoção confirmada.
"""

import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, get_args

from pydantic import ValidationError

from src.artifacts.contracts import ArtifactError, RetainedCatalogRef
from src.artifacts.storage import LocalArtifactStore
from src.domain_catalog.actor import ActorSnapshot
from src.domain_catalog.contracts import CatalogReleaseRef
from src.domain_catalog.curation import revision_key, utc_now
from src.domain_catalog.curation_models import (
    DraftRevision,
    PublicationIntent,
    PublicationReceipt,
    ReleaseCandidate,
    ReviewRecord,
)
from src.domain_catalog.diff import diff_catalogs
from src.domain_catalog.migration_contracts import (
    AdoptionIntent,
    AdoptionReceipt,
    CatalogAdoptionPlan,
    FrozenPair,
    MigrationError,
    MigrationErrorReason,
    ReanalysisReceipt,
    RetainedReleaseRecord,
    plan_digest,
)
from src.domain_catalog.package import ContentOrigin, PackageLimits
from src.domain_catalog.provenance import CatalogProvenance
from src.domain_catalog.publication import publication_key
from src.domain_catalog.reader import CatalogReader
from src.operations.analysis_queue import (
    AnalysisQueueReceipt,
    AnalysisQueueService,
    diagnose_catalog,
    load_pin,
    load_project,
    new_run,
    parent_of,
    queued_event,
    retained_release,
)
from src.operations.command_runner import Effect, OperationalRunner
from src.operations.contracts import (
    OperationalCommand,
    OperationalError,
    OperationalReceipt,
    ResultingRef,
    canonical_sha256,
    new_uuid,
    require_tokens,
)
from src.operations.database import (
    OperationalStore,
    OperationalUnitOfWork,
    ReleaseHashCollisionError,
)
from src.operations.project_models import ModelPairBinding, ProjectCatalogPin
from src.validation.analysis_identity import (
    AnalysisRun,
    ExecutionProfile,
    current_execution_profile,
)
from src.validation.diagnostic_models import DiagnosticSnapshot

_MIGRATION_REASONS = frozenset(get_args(MigrationErrorReason))


def _converted(
    exc: OperationalError, project_id: uuid.UUID | None, plan_id: uuid.UUID | None
) -> Exception:
    if exc.reason in _MIGRATION_REASONS:
        error = MigrationError(
            exc.reason,  # type: ignore[arg-type]
            str(exc),
            project_id=project_id,
            plan_id=plan_id,
            expected=exc.expected,
            actual=exc.actual,
        )
        error.__cause__ = exc
        return error
    return exc


def _artifact(
    exc: ArtifactError, project_id: uuid.UUID, plan_id: uuid.UUID | None
) -> MigrationError:
    reason: MigrationErrorReason = (
        "artifact_unavailable"
        if exc.reason == "artifact_unavailable"
        else "artifact_integrity_error"
    )
    error = MigrationError(reason, str(exc), project_id=project_id, plan_id=plan_id)
    error.__cause__ = exc
    return error


def resolve_provenance(
    uow: OperationalUnitOfWork, ref: CatalogReleaseRef, content_origin: ContentOrigin
) -> CatalogProvenance:
    """Proveniência obtida da cadeia E2 histórica exata; sem cadeia é ``unverified_package``.

    Diretório, manifesto ``curated``, aceite de pin ou recibo isolado não bastam. A
    mesma versão publicada com outro hash é ``version_hash_collision``. Fixture
    sintética com cadeia válida num banco operacional é ``synthetic_catalog_forbidden``.
    """
    unverified = CatalogProvenance(
        state="unverified_package",
        catalog=ref,
        content_origin=content_origin,
        store_purpose=uow.purpose,
    )
    row = uow.curation.get("publication", publication_key(ref.catalog_id, ref.version))
    if row is None:
        return unverified
    try:
        receipt = PublicationReceipt.model_validate(row.document)
    except ValidationError:
        return unverified
    if receipt.release != ref:
        raise MigrationError(
            "version_hash_collision",
            f"versão {ref.version} publicada com outro manifesto",
            expected=receipt.release.manifest_sha256,
            actual=ref.manifest_sha256,
        )
    if not _chain_is_complete(uow, receipt) or receipt.content_origin != content_origin:
        return unverified
    if content_origin == "synthetic_fixture" and uow.purpose != "synthetic_test":
        raise MigrationError(
            "synthetic_catalog_forbidden",
            "fixture sintética não é adotável num banco de propósito operational",
        )
    return CatalogProvenance(
        state="published_local" if content_origin == "curated" else "synthetic_test_published",
        catalog=ref,
        content_origin=content_origin,
        store_purpose=uow.purpose,
        receipt_id=receipt.receipt_id,
        receipt_sha256=canonical_sha256(row.document),
        candidate_id=receipt.candidate_id,
        intent_id=receipt.intent_id,
        draft_id=receipt.draft_id,
        revision=receipt.revision,
        content_sha256=receipt.content_sha256,
        approval_id=receipt.approval_id,
    )


def _record(uow: OperationalUnitOfWork, kind: str, key: str, model: type[Any]) -> Any:
    row = uow.curation.get(kind, key)
    if row is None:
        return None
    try:
        return model.model_validate(row.document)
    except ValidationError:
        return None


def _chain_is_complete(uow: OperationalUnitOfWork, receipt: PublicationReceipt) -> bool:
    """Candidato, intenção, revisão, aprovação, validação e atores exatos e finais."""
    candidate = _record(uow, "candidate", receipt.candidate_id, ReleaseCandidate)
    intent = _record(uow, "intent", receipt.intent_id, PublicationIntent)
    revision = _record(
        uow, "revision", revision_key(receipt.draft_id, receipt.revision), DraftRevision
    )
    approval = _record(uow, "review", receipt.approval_id, ReviewRecord)
    if None in (candidate, intent, revision, approval):
        return False
    # Cada nó e aresta é conferido contra o recibo, sem depender do head atual: registro
    # válido e re-hasheado de outro encadeamento não passa (E3-12).
    checks = (
        candidate.state == "published",
        candidate.candidate_id == receipt.candidate_id,
        candidate.release == receipt.release,
        candidate.previous_release == receipt.previous_release,
        (candidate.draft_id, candidate.revision, candidate.content_sha256)
        == (receipt.draft_id, receipt.revision, receipt.content_sha256),
        candidate.approval_id == receipt.approval_id,
        candidate.validation == receipt.validation,
        candidate.pending_items == receipt.pending_items,
        candidate.content_origin == receipt.content_origin,
        receipt.validation.errors == 0,
        intent.state == "completed",
        intent.intent_id == receipt.intent_id,
        (intent.candidate_id, intent.release) == (receipt.candidate_id, receipt.release),
        (intent.publisher, intent.justification, intent.acknowledged_pending, intent.command_id)
        == (
            receipt.published_by,
            receipt.publication_justification,
            receipt.acknowledged_pending,
            receipt.command_id,
        ),
        (revision.draft_id, revision.revision, revision.content_sha256)
        == (receipt.draft_id, receipt.revision, receipt.content_sha256),
        (approval.review_id, approval.draft_id, approval.revision)
        == (receipt.approval_id, receipt.draft_id, receipt.revision),
        (approval.verdict, approval.content_sha256) == ("approve", receipt.content_sha256),
        (approval.reviewer, approval.justification)
        == (receipt.approved_by, receipt.approval_justification),
        receipt.approved_by.actor_kind == "human",
        receipt.published_by.actor_kind == "human",
    )
    if not all(checks):
        return False
    for snapshot in (receipt.approved_by, receipt.published_by, receipt.completed_by):
        context = uow.actors.get(snapshot.actor_context_id)
        if context is None or context.document["actor_kind"] != snapshot.actor_kind:
            return False
    return True


def adoption_arguments(*, plan_id: uuid.UUID, confirmed_plan_sha256: str) -> dict[str, Any]:
    """Argumentos de ``apply_catalog_adoption``: só ID e hash confirmados."""
    return {"plan_id": str(plan_id), "confirmed_plan_sha256": confirmed_plan_sha256}


def adoption_command(
    command_id: uuid.UUID,
    actor: uuid.UUID,
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    confirmed_plan_sha256: str,
) -> OperationalCommand:
    """Envelope da confirmação explícita do plano."""
    return OperationalCommand.build(
        command_id=command_id,
        actor_context_id=actor,
        operation="apply_catalog_adoption",
        project_id=project_id,
        arguments=adoption_arguments(plan_id=plan_id, confirmed_plan_sha256=confirmed_plan_sha256),
    )


def reanalysis_arguments(
    *,
    project_id: uuid.UUID,
    expected_pin_revision: int,
    expected_pair_set_revision: int,
    execution_profile: ExecutionProfile,
    reason: str,
) -> dict[str, Any]:
    """Argumentos de ``queue_reanalysis``."""
    return {
        "project_id": str(project_id),
        "expected_pin_revision": expected_pin_revision,
        "expected_pair_set_revision": expected_pair_set_revision,
        "execution_profile": execution_profile.model_dump(mode="json"),
        "reason": reason,
    }


def reanalysis_command(
    command_id: uuid.UUID,
    actor: uuid.UUID,
    project_id: uuid.UUID,
    expected_pin_revision: int,
    expected_pair_set_revision: int,
    execution_profile: ExecutionProfile,
    reason: str,
) -> OperationalCommand:
    """Envelope de ``queue_reanalysis``."""
    return OperationalCommand.build(
        command_id=command_id,
        actor_context_id=actor,
        operation="queue_reanalysis",
        project_id=project_id,
        arguments=reanalysis_arguments(
            project_id=project_id,
            expected_pin_revision=expected_pin_revision,
            expected_pair_set_revision=expected_pair_set_revision,
            execution_profile=execution_profile,
            reason=reason,
        ),
    )


class CatalogAdoptionService:
    """Adoção/atualização/rollback de catálogo e reanálise, na autoridade comum."""

    def __init__(
        self,
        store: OperationalStore,
        artifacts: LocalArtifactStore,
        *,
        clock: Callable[[], str] = utc_now,
        new_id: Callable[[], uuid.UUID] = new_uuid,
        package_limits: PackageLimits | None = None,
    ) -> None:
        """Banco operacional, artefatos retidos, relógio e gerador de IDs."""
        self._store = store
        self._artifacts = artifacts
        self._runner = OperationalRunner(store, clock=clock, new_id=new_id)
        self._queue = AnalysisQueueService(store, artifacts, clock=clock, new_id=new_id)
        self._clock = clock
        self._new_id = new_id
        self._limits = package_limits

    @staticmethod
    def plan_sha256(plan: CatalogAdoptionPlan) -> str:
        """Hash que a confirmação precisa citar."""
        return plan_digest(plan)

    def load_plan(self, plan_id: uuid.UUID) -> CatalogAdoptionPlan:
        """Plano persistido; ausência é ``not_found``."""
        with self._store.transaction() as uow:
            row = uow.adoption_plans.get(str(plan_id))
        if row is None:
            raise MigrationError("not_found", f"plano {plan_id} não existe", plan_id=plan_id)
        return CatalogAdoptionPlan.model_validate(row.document)

    def list_runs(self, project_id: uuid.UUID) -> list[AnalysisRun]:
        """Runs do projeto em ordem de enfileiramento."""
        return self._queue.list_runs(project_id)

    def _open(
        self, retained: RetainedCatalogRef, project_id: uuid.UUID, plan_id: uuid.UUID | None
    ) -> CatalogReader:
        try:
            return self._artifacts.open_retained_catalog(retained, limits=self._limits)
        except ArtifactError as exc:
            raise _artifact(exc, project_id, plan_id) from exc

    # --- preparação -----------------------------------------------------------------------

    def prepare_catalog_adoption(
        self,
        *,
        project_id: uuid.UUID,
        expected_pin_revision: int,
        expected_pair_set_revision: int,
        target_ref: CatalogReleaseRef,
        target_dir: Path,
        intent: AdoptionIntent,
        reason: str,
        execution_profile: ExecutionProfile,
        prepared_by_actor_context_id: uuid.UUID,
    ) -> CatalogAdoptionPlan:
        """Plano imutável e persistido; não altera pin nem enfileira análise."""
        if not reason.strip():
            raise MigrationError("invalid_command", "motivo obrigatório", project_id=project_id)
        try:
            require_tokens(
                expected_pin_revision=expected_pin_revision,
                expected_pair_set_revision=expected_pair_set_revision,
            )
        except OperationalError as exc:
            raise _converted(exc, project_id, None) from exc
        try:
            actor = self._runner.actors.require(
                str(prepared_by_actor_context_id), requirement="any"
            )
        except OperationalError as exc:
            raise _converted(exc, project_id, None) from exc
        try:
            retained = self._artifacts.retain_catalog(target_ref, target_dir, limits=self._limits)
        except ArtifactError as exc:
            raise _artifact(exc, project_id, None) from exc
        target_reader = self._open(retained, project_id, None)
        try:
            with self._store.transaction() as uow:
                frozen = self._frozen_state(
                    uow,
                    project_id,
                    expected_pin_revision,
                    expected_pair_set_revision,
                    target_ref,
                    intent,
                    retained,
                )
        except OperationalError as exc:
            raise _converted(exc, project_id, None) from exc
        pin, pairs, provenance, old_retained, informative = frozen
        diff = None
        if pin is not None:
            assert old_retained is not None
            old_reader = self._open(old_retained, project_id, None)
            diff = diff_catalogs(old_reader, target_reader)
        plan = CatalogAdoptionPlan(
            plan_id=self._new_id(),
            project_id=project_id,
            intent=intent,
            reason=reason,
            old_pin_revision=0 if pin is None else pin.pin_revision,
            old_ref=None if pin is None else pin.catalog,
            target_ref=target_ref,
            target_retained=retained,
            target_provenance=provenance,
            expected_pin_revision=expected_pin_revision,
            expected_pair_set_revision=expected_pair_set_revision,
            pairs=pairs,
            execution_profile=execution_profile,
            diff=diff,
            diff_sha256=None if diff is None else canonical_sha256(diff.model_dump(mode="json")),
            diff_absent_reason="no_previous_catalog" if diff is None else None,
            informative_requirement_refs=informative,
            prepared_by=actor,
            prepared_at_utc=self._clock(),
        )
        try:
            with self._store.transaction() as uow:
                self._record_release(uow, retained)
                uow.adoption_plans.insert(plan.model_dump(mode="json"))
                uow.events.append(
                    "operations",
                    {
                        "event": "adoption_plan_prepared",
                        "plan_id": str(plan.plan_id),
                        "plan_sha256": plan_digest(plan),
                        "project_id": str(project_id),
                        "intent": intent,
                        "target_version": target_ref.version,
                        "target_manifest_sha256": target_ref.manifest_sha256,
                        "actor_context_id": actor.actor_context_id,
                        "at_utc": plan.prepared_at_utc,
                    },
                )
        except ReleaseHashCollisionError as exc:
            raise MigrationError("version_hash_collision", str(exc), project_id=project_id) from exc
        return plan

    def _record_release(self, uow: OperationalUnitOfWork, retained: RetainedCatalogRef) -> None:
        record = RetainedReleaseRecord(
            catalog=retained.catalog,
            storage_key=retained.storage_key,
            retained=retained,
            content_origin=retained.content_origin,
        )
        uow.releases.insert_or_verify(record.model_dump(mode="json"))

    def _frozen_state(
        self,
        uow: OperationalUnitOfWork,
        project_id: uuid.UUID,
        expected_pin_revision: int,
        expected_pair_set_revision: int,
        target_ref: CatalogReleaseRef,
        intent: AdoptionIntent,
        retained: RetainedCatalogRef,
    ) -> tuple[
        ProjectCatalogPin | None,
        tuple[FrozenPair, ...],
        CatalogProvenance,
        RetainedCatalogRef | None,
        tuple[str, ...],
    ]:
        project, _ = load_project(uow, project_id)
        pin = load_pin(uow, project_id)
        current = 0 if pin is None else pin.pin_revision
        if current != expected_pin_revision:
            raise OperationalError(
                "stale_pin", "pin mudou", expected=expected_pin_revision, actual=current
            )
        if project.pair_set_revision != expected_pair_set_revision:
            raise OperationalError(
                "stale_pair_set",
                "conjunto de pares mudou",
                expected=expected_pair_set_revision,
                actual=project.pair_set_revision,
            )
        if (intent == "initial") != (pin is None):
            raise MigrationError(
                "intent_mismatch",
                "initial exige projeto sem pin; update/rollback exigem pin",
                project_id=project_id,
            )
        if intent == "rollback":
            history = {
                (
                    row.document["catalog"]["catalog_id"],
                    row.document["catalog"]["version"],
                    row.document["catalog"]["manifest_sha256"],
                )
                for row in uow.pins.scan_revisions(project_id=str(project_id))
            }
            key = (target_ref.catalog_id, target_ref.version, target_ref.manifest_sha256)
            if key not in history:
                raise MigrationError(
                    "intent_mismatch",
                    "rollback exige alvo já fixado neste projeto",
                    project_id=project_id,
                )
        if not project.active_pair_refs:
            raise MigrationError("no_active_pairs", "projeto sem par ativo", project_id=project_id)
        existing = uow.releases.get(target_ref.catalog_id, target_ref.version)
        if (
            existing is not None
            and existing.document["catalog"]["manifest_sha256"] != target_ref.manifest_sha256
        ):
            raise MigrationError(
                "version_hash_collision",
                f"{target_ref.version} já retido com outro manifesto",
                project_id=project_id,
                expected=existing.document["catalog"]["manifest_sha256"],
                actual=target_ref.manifest_sha256,
            )
        provenance = resolve_provenance(uow, target_ref, retained.content_origin)
        if not provenance.published:
            raise MigrationError(
                "unpublished_release",
                "release sem cadeia de publicação verificável na autoridade",
                project_id=project_id,
            )
        old_retained = None if pin is None else retained_release(uow, pin)
        pairs = tuple(
            FrozenPair(pair=pair, parent_analysis_id=parent_of(uow, pair.pair_id))
            for pair in project.active_pair_refs
        )
        informative: list[str] = []
        for frozen in pairs:
            if frozen.parent_analysis_id is None:
                continue
            for row in uow.diagnostics.scan(analysis_id=str(frozen.parent_analysis_id)):
                snapshot = DiagnosticSnapshot.model_validate(row.document)
                informative.extend(r.requirement.key() for r in snapshot.requirements)
        return pin, pairs, provenance, old_retained, tuple(sorted(set(informative)))

    # --- aplicação ------------------------------------------------------------------------

    def apply_catalog_adoption(
        self, *, command: OperationalCommand, plan_id: uuid.UUID, confirmed_plan_sha256: str
    ) -> AdoptionReceipt:
        """Confirmação explícita do plano exato; tudo ou nada; replay devolve o original."""
        plan = self.load_plan(plan_id)
        project_id = plan.project_id
        arguments = adoption_arguments(plan_id=plan_id, confirmed_plan_sha256=confirmed_plan_sha256)
        try:
            self._runner.verify_envelope(
                command,
                operation="apply_catalog_adoption",
                project_id=project_id,
                arguments=arguments,
            )
            found = self._runner.lookup(command)
            if found is not None:
                return AdoptionReceipt.model_validate(found.result)
            if plan_digest(plan) != confirmed_plan_sha256:
                raise MigrationError(
                    "plan_hash_mismatch",
                    "hash confirmado não é o do plano persistido",
                    project_id=project_id,
                    plan_id=plan_id,
                    expected=plan_digest(plan),
                    actual=confirmed_plan_sha256,
                )
            current_profile = current_execution_profile(plan.execution_profile.limits)
            if current_profile != plan.execution_profile:
                raise MigrationError(
                    "execution_profile_mismatch",
                    "runtime atual não cumpre o perfil do plano",
                    project_id=project_id,
                    plan_id=plan_id,
                )
            self._open(plan.target_retained, project_id, plan_id)
            if plan.old_ref is not None:
                # O diff revisado depende do release anterior: reaberto também (E3-13).
                self._open(self._old_retained(plan), project_id, plan_id)
            outcome = self._runner.run(
                command,
                operation="apply_catalog_adoption",
                project_id=project_id,
                arguments=arguments,
                requirement="human",
                body=lambda uow, actor, now: self._apply_body(uow, actor, now, plan),
            )
        except OperationalError as exc:
            raise _converted(exc, project_id, plan_id) from exc
        return AdoptionReceipt.model_validate(outcome.result)

    def _old_retained(self, plan: CatalogAdoptionPlan) -> RetainedCatalogRef:
        """Release anterior exato do plano, pelo registro da autoridade."""
        assert plan.old_ref is not None
        with self._store.transaction() as uow:
            row = uow.releases.get(plan.old_ref.catalog_id, plan.old_ref.version)
        if row is None:
            raise MigrationError(
                "artifact_unavailable",
                "release anterior do plano sem registro retido",
                project_id=plan.project_id,
                plan_id=plan.plan_id,
            )
        retained = RetainedCatalogRef.model_validate(row.document["retained"])
        if retained.catalog != plan.old_ref:
            raise MigrationError(
                "artifact_integrity_error",
                "registro retido difere do release anterior do plano",
                project_id=plan.project_id,
                plan_id=plan.plan_id,
            )
        return retained

    def _apply_body(
        self, uow: OperationalUnitOfWork, actor: ActorSnapshot, now: str, plan: CatalogAdoptionPlan
    ) -> Effect:
        project_id, plan_id = plan.project_id, plan.plan_id
        project, _ = load_project(uow, project_id)
        pin = load_pin(uow, project_id)
        current = 0 if pin is None else pin.pin_revision
        if (
            current != plan.expected_pin_revision
            or (None if pin is None else pin.catalog) != plan.old_ref
        ):
            raise MigrationError(
                "stale_pin",
                "pin mudou depois do plano",
                project_id=project_id,
                plan_id=plan_id,
                expected=plan.expected_pin_revision,
                actual=current,
            )
        if project.pair_set_revision != plan.expected_pair_set_revision:
            raise MigrationError(
                "stale_pair_set",
                "conjunto de pares mudou depois do plano",
                project_id=project_id,
                plan_id=plan_id,
                expected=plan.expected_pair_set_revision,
                actual=project.pair_set_revision,
            )
        frozen = tuple(
            FrozenPair(pair=pair, parent_analysis_id=parent_of(uow, pair.pair_id))
            for pair in project.active_pair_refs
        )
        if frozen != plan.pairs:
            raise MigrationError(
                "stale_plan",
                "pares ou análises anteriores mudaram depois do plano",
                project_id=project_id,
                plan_id=plan_id,
            )
        provenance = resolve_provenance(uow, plan.target_ref, plan.target_retained.content_origin)
        if provenance != plan.target_provenance:
            raise MigrationError(
                "unpublished_release" if not provenance.published else "stale_plan",
                "cadeia de publicação do alvo difere da conferida no plano",
                project_id=project_id,
                plan_id=plan_id,
            )
        self._record_release(uow, plan.target_retained)
        digest = plan_digest(plan)
        if pin is not None and pin.catalog == plan.target_ref:

            def noop(receipt: OperationalReceipt) -> AdoptionReceipt:
                return AdoptionReceipt(
                    operational=receipt,
                    project_id=project_id,
                    plan_id=plan_id,
                    plan_sha256=digest,
                    intent=plan.intent,
                    status="noop",
                )

            return Effect(
                "noop",
                (ResultingRef(kind="adoption_plan", ref_id=plan_id),),
                (
                    {
                        "event": "catalog_adoption_noop",
                        "plan_id": str(plan_id),
                        "pin_revision": current,
                        "manifest_sha256": plan.target_ref.manifest_sha256,
                    },
                ),
                finalize=noop,
            )
        adoption_id = self._new_id()
        new_pin = ProjectCatalogPin(
            project_id=project_id,
            pin_revision=current + 1,
            catalog=plan.target_ref,
            catalog_provenance=provenance,
            adoption_id=adoption_id,
            previous_pin_revision=None if pin is None else current,
            actor_snapshot=actor,
            reason=plan.reason,
            created_at_utc=now,
        )
        uow.pins.insert_revision(new_pin.model_dump(mode="json"))
        head = {"project_id": str(project_id), "pin_revision": new_pin.pin_revision}
        existing_head = uow.pins.get_head(str(project_id))
        if existing_head is None:
            uow.pins.insert_head(head)
        else:
            uow.pins.replace_head(str(project_id), existing_head.row_version, head)
        catalog_state = diagnose_catalog(self._artifacts, plan.target_retained)
        runs = [
            new_run(
                analysis_id=self._new_id(),
                pair=item.pair,
                pin=new_pin,
                catalog_state=catalog_state,
                profile=plan.execution_profile,
                actor=actor,
                reason=f"adoção {plan.intent}: {plan.reason}",
                now=now,
                parent=item.parent_analysis_id,
            )
            for item in plan.pairs
        ]
        for run in runs:
            uow.analyses.insert(run.model_dump(mode="json"))
        event_name = "catalog_rolled_back" if plan.intent == "rollback" else "catalog_adopted"
        events: list[dict[str, Any]] = [
            {
                "event": event_name,
                "plan_id": str(plan_id),
                "plan_sha256": digest,
                "adoption_id": str(adoption_id),
                "pin_revision": new_pin.pin_revision,
                "catalog_version": plan.target_ref.version,
                "manifest_sha256": plan.target_ref.manifest_sha256,
                "analysis_ids": [str(run.analysis_id) for run in runs],
            },
            *(queued_event(run) for run in runs),
        ]

        def applied(receipt: OperationalReceipt) -> AdoptionReceipt:
            return AdoptionReceipt(
                operational=receipt,
                project_id=project_id,
                plan_id=plan_id,
                plan_sha256=digest,
                intent=plan.intent,
                status="applied",
                adoption_id=adoption_id,
                pin=new_pin,
                queued_analysis_ids=tuple(run.analysis_id for run in runs),
            )

        return Effect(
            "applied",
            (
                ResultingRef(kind="adoption", ref_id=adoption_id),
                ResultingRef(kind="pin", ref_id=project_id, revision=new_pin.pin_revision),
                *(ResultingRef(kind="analysis", ref_id=run.analysis_id) for run in runs),
            ),
            tuple(events),
            finalize=applied,
        )

    # --- reanálise ------------------------------------------------------------------------

    def queue_reanalysis(
        self,
        *,
        command: OperationalCommand,
        project_id: uuid.UUID,
        expected_pin_revision: int,
        expected_pair_set_revision: int,
        execution_profile: ExecutionProfile,
        reason: str,
    ) -> ReanalysisReceipt:
        """Repete a análise de todos os pares ativos sem trocar o pin."""
        try:
            require_tokens(
                expected_pin_revision=expected_pin_revision,
                expected_pair_set_revision=expected_pair_set_revision,
            )
        except OperationalError as exc:
            raise _converted(exc, project_id, None) from exc
        arguments = reanalysis_arguments(
            project_id=project_id,
            expected_pin_revision=expected_pin_revision,
            expected_pair_set_revision=expected_pair_set_revision,
            execution_profile=execution_profile,
            reason=reason,
        )
        try:
            self._runner.verify_envelope(
                command, operation="queue_reanalysis", project_id=project_id, arguments=arguments
            )
            found = self._runner.lookup(command)
            if found is not None:
                return AnalysisQueueReceipt.model_validate(found.result)
            if current_execution_profile(execution_profile.limits) != execution_profile:
                raise MigrationError(
                    "execution_profile_mismatch",
                    "runtime atual não cumpre o perfil",
                    project_id=project_id,
                )
            with self._store.transaction() as uow:
                pin = load_pin(uow, project_id)
                retained = None if pin is None else retained_release(uow, pin)
            catalog_state = diagnose_catalog(self._artifacts, retained)

            def body(uow: OperationalUnitOfWork, actor: ActorSnapshot, now: str) -> Effect:
                project, _ = load_project(uow, project_id)
                current_pin = load_pin(uow, project_id)
                current = 0 if current_pin is None else current_pin.pin_revision
                if current != expected_pin_revision or current_pin != pin:
                    raise MigrationError(
                        "stale_pin",
                        "pin mudou",
                        project_id=project_id,
                        expected=expected_pin_revision,
                        actual=current,
                    )
                if project.pair_set_revision != expected_pair_set_revision:
                    raise MigrationError(
                        "stale_pair_set",
                        "conjunto de pares mudou",
                        project_id=project_id,
                        expected=expected_pair_set_revision,
                        actual=project.pair_set_revision,
                    )
                if not project.active_pair_refs:
                    raise MigrationError(
                        "no_active_pairs", "projeto sem par ativo", project_id=project_id
                    )
                runs = [
                    new_run(
                        analysis_id=self._new_id(),
                        pair=pair,
                        pin=pin,
                        catalog_state=catalog_state,
                        profile=execution_profile,
                        actor=actor,
                        reason=reason,
                        now=now,
                        parent=parent_of(uow, pair.pair_id),
                    )
                    for pair in project.active_pair_refs
                ]
                for run in runs:
                    uow.analyses.insert(run.model_dump(mode="json"))

                def finalize(receipt: OperationalReceipt) -> AnalysisQueueReceipt:
                    return AnalysisQueueReceipt(
                        operational=receipt,
                        project_id=project_id,
                        pin_revision=current,
                        queued_analysis_ids=tuple(run.analysis_id for run in runs),
                    )

                return Effect(
                    "applied",
                    tuple(ResultingRef(kind="analysis", ref_id=run.analysis_id) for run in runs),
                    tuple(queued_event(run) for run in runs),
                    finalize=finalize,
                )

            outcome = self._runner.run(
                command,
                operation="queue_reanalysis",
                project_id=project_id,
                arguments=arguments,
                requirement="human_or_service",
                body=body,
            )
        except OperationalError as exc:
            raise _converted(exc, project_id, None) from exc
        return AnalysisQueueReceipt.model_validate(outcome.result)


__all__ = [
    "CatalogAdoptionService",
    "ModelPairBinding",
    "adoption_command",
    "reanalysis_command",
    "resolve_provenance",
]
