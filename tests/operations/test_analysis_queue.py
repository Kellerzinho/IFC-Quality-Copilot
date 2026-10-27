"""Fila de análises: identidade congelada, estado do catálogo e transições monotônicas."""

import shutil
import sqlite3
import uuid
from pathlib import Path

import pytest

pytest.importorskip("ifctester", reason="extra e3 não instalado (ifctester==0.8.5)")

from src.operations.analysis_queue import (
    AnalysisQueueReceipt,
    AnalysisQueueService,
    initial_analysis_command,
)
from src.operations.contracts import OperationalError
from src.validation.analysis_identity import current_execution_profile
from tests.domain_catalog import factories as f
from tests.operations.adoption_env import (
    AdoptionEnv,
    apply,
    make_adoption_env,
    prepare,
)
from tests.operations.e3_env import publish_first


def _queue(
    aenv: AdoptionEnv, *, actor: uuid.UUID | None = None, key: uuid.UUID | None = None
) -> tuple[AnalysisQueueService, AnalysisQueueReceipt]:
    state = aenv.projects.load_project_state(aenv.project_id)
    pair = state.pairs[0]
    profile = current_execution_profile()
    service = AnalysisQueueService(aenv.env.store, aenv.env.artifacts)
    return service, service.queue_initial_analysis(
        command=initial_analysis_command(
            key or uuid.uuid4(),
            actor or aenv.human,
            aenv.project_id,
            pair.pair_id,
            pair.pair_revision,
            state.pair_set_revision,
            profile,
        ),
        project_id=aenv.project_id,
        pair_id=pair.pair_id,
        expected_pair_revision=pair.pair_revision,
        expected_pair_set_revision=state.pair_set_revision,
        execution_profile=profile,
    )


def test_first_analysis_without_catalog_is_not_attached(tmp_path: Path) -> None:
    aenv = make_adoption_env(tmp_path)
    key = uuid.uuid4()
    service, receipt = _queue(aenv, key=key)
    (analysis_id,) = receipt.queued_analysis_ids
    run = service.load_run(analysis_id)

    assert run.state == "queued"
    assert run.identity.catalog_state == "not_attached"
    assert (run.identity.catalog_ref, run.identity.pin_revision) == (None, None)
    assert _queue(aenv, key=key)[1] == receipt
    with pytest.raises(OperationalError) as assistant:
        _queue(aenv, actor=aenv.assistant)
    assert assistant.value.reason == "invalid_actor"


def test_with_pin_the_exact_pin_is_used_and_cannot_be_omitted(tmp_path: Path) -> None:
    aenv = make_adoption_env(tmp_path)
    published = publish_first(aenv.env, f.minimal_content("draft"))
    apply(aenv, prepare(aenv, published.release, "initial"))
    service, receipt = _queue(aenv)
    run = service.load_run(receipt.queued_analysis_ids[0])

    assert run.identity.catalog_state == "available"
    assert (run.identity.catalog_ref, run.identity.pin_revision) == (published.release, 1)
    assert run.identity.catalog_provenance is not None
    assert run.identity.catalog_provenance.state == "synthetic_test_published"


@pytest.mark.parametrize("damage", ["missing", "tampered"])
def test_damaged_retained_catalog_keeps_expected_ref_with_diagnosed_state(
    tmp_path: Path, damage: str
) -> None:
    aenv = make_adoption_env(tmp_path)
    published = publish_first(aenv.env, f.minimal_content("draft"))
    plan = prepare(aenv, published.release, "initial")
    apply(aenv, plan)
    folder = aenv.env.artifacts.catalog_dir(plan.target_retained)
    if damage == "missing":
        shutil.move(folder, folder.with_name("fora"))
    else:
        (folder / "concepts.json").write_bytes((folder / "concepts.json").read_bytes() + b" ")
    service, receipt = _queue(aenv)
    run = service.load_run(receipt.queued_analysis_ids[0])

    assert run.identity.catalog_state == ("unavailable" if damage == "missing" else "invalid")
    assert (run.identity.catalog_ref, run.identity.pin_revision) == (published.release, 1)


def test_queue_refuses_stale_pair_and_frozen_identity_is_immutable(tmp_path: Path) -> None:
    aenv = make_adoption_env(tmp_path)
    state = aenv.projects.load_project_state(aenv.project_id)
    pair = state.pairs[0]
    profile = current_execution_profile()
    service = AnalysisQueueService(aenv.env.store, aenv.env.artifacts)
    with pytest.raises(OperationalError) as stale:
        service.queue_initial_analysis(
            command=initial_analysis_command(
                uuid.uuid4(),
                aenv.human,
                aenv.project_id,
                pair.pair_id,
                2,
                state.pair_set_revision,
                profile,
            ),
            project_id=aenv.project_id,
            pair_id=pair.pair_id,
            expected_pair_revision=2,
            expected_pair_set_revision=state.pair_set_revision,
            execution_profile=profile,
        )
    assert stale.value.reason == "stale_pair"
    _, receipt = _queue(aenv)
    with sqlite3.connect(aenv.env.store.path) as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "UPDATE analysis_runs SET identity_sha256 = ? WHERE analysis_id = ?",
            ("0" * 64, str(receipt.queued_analysis_ids[0])),
        )


def test_profile_the_runtime_cannot_fulfil_is_refused(tmp_path: Path) -> None:
    aenv = make_adoption_env(tmp_path)
    state = aenv.projects.load_project_state(aenv.project_id)
    pair = state.pairs[0]
    other = current_execution_profile().model_copy(update={"condition_config_sha256": "e" * 64})
    service = AnalysisQueueService(aenv.env.store, aenv.env.artifacts)
    with pytest.raises(OperationalError) as refused:
        service.queue_initial_analysis(
            command=initial_analysis_command(
                uuid.uuid4(),
                aenv.human,
                aenv.project_id,
                pair.pair_id,
                1,
                state.pair_set_revision,
                other,
            ),
            project_id=aenv.project_id,
            pair_id=pair.pair_id,
            expected_pair_revision=1,
            expected_pair_set_revision=state.pair_set_revision,
            execution_profile=other,
        )
    assert refused.value.reason == "execution_profile_mismatch"


def test_run_transitions_are_monotonic_and_terminal_rows_are_immutable(tmp_path: Path) -> None:
    aenv = make_adoption_env(tmp_path)
    service, receipt = _queue(aenv)
    run = service.load_run(receipt.queued_analysis_ids[0])
    with pytest.raises(ValueError):
        run.advance("completed")
    with sqlite3.connect(aenv.env.store.path) as conn:
        conn.execute("DROP TRIGGER IF EXISTS analysis_runs_identity")
    with sqlite3.connect(aenv.env.store.path) as conn:
        conn.execute(
            "UPDATE analysis_runs SET state = 'failed' WHERE analysis_id = ?",
            (str(receipt.queued_analysis_ids[0]),),
        )
    with sqlite3.connect(aenv.env.store.path) as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "UPDATE analysis_runs SET state = 'queued' WHERE analysis_id = ?",
            (str(receipt.queued_analysis_ids[0]),),
        )


def test_run_state_advances_by_cas_while_identity_columns_stay_immutable(
    tmp_path: Path,
) -> None:
    from src.domain_catalog.curation import utc_now
    from src.domain_catalog.draft_store import StoreConflictError
    from src.validation.analysis_identity import AnalysisRun, ExecutionClaim

    aenv = make_adoption_env(tmp_path)
    _, receipt = _queue(aenv)
    analysis_id = str(receipt.queued_analysis_ids[0])
    store = aenv.env.store
    with store.transaction() as uow:
        row = uow.analyses.get(analysis_id)
        assert row is not None
        now = utc_now()
        claim = ExecutionClaim(
            execution_token=uuid.uuid4(),
            coordinator_token=uuid.uuid4(),
            command_id=uuid.uuid4(),
            claimed_at_utc=now,
        )
        running = AnalysisRun.model_validate(row.document).advance(
            "running", claim=claim, started_at_utc=now
        )
        updated = uow.analyses.replace(
            analysis_id, row.row_version, running.model_dump(mode="json")
        )
    assert updated.document["state"] == "running"

    document = running.model_dump(mode="json")
    forged = {**document, "identity": {**document["identity"], "pair_revision": 9}}
    with pytest.raises(StoreConflictError), store.transaction() as uow:
        uow.analyses.replace(analysis_id, updated.row_version, forged)
