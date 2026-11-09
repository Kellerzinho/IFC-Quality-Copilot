"""Execução durável de análises: claim, lock do coordenador, recuperação, replay e queda (A06, A23).

Autoridade SQLite, artefatos, publicação E2, backend IDS e operações M3 REAIS; projeto,
atores, catálogo e fontes SINTÉTICOS. Processos de verdade provam o lock do sistema
operacional e as quedas antes/depois do commit.
"""

import os
import sqlite3
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

pytest.importorskip("ifctester", reason="extra e3 não instalado (ifctester==0.8.5)")

from src.operations.contracts import OperationalError
from src.operations.repositories import encode_document
from src.pipeline import run_catalog_analysis
from src.suggestion_engine.catalog_service import CatalogEnrichmentService
from src.validation.analysis_identity import AnalysisRun
from src.validation.catalog_analysis import (
    AnalysisCoordinator,
    CatalogAnalysisReceipt,
    CatalogAnalysisRequest,
    load_analysis,
)
from tests.operations import analysis_env as ae
from tests.operations.adoption_env import AdoptionEnv, apply, prepare, reanalyze
from tests.operations.e3_env import publish_first

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def adopted(tmp_path: Path) -> tuple[AdoptionEnv, list[AnalysisRun]]:
    aenv = ae.make_analysis_env(tmp_path / "env")
    release = publish_first(aenv.env, ae.catalog()).release
    receipt = apply(aenv, prepare(aenv, release, "initial"))
    return aenv, ae.runs_in_pair_order(aenv, receipt.queued_analysis_ids)


def _execute(aenv: AdoptionEnv, request: CatalogAnalysisRequest) -> CatalogAnalysisReceipt:
    return run_catalog_analysis(
        request,
        store=aenv.env.store,
        artifacts=aenv.env.artifacts,
        operation_bundle=ae.operation_bundle(),
    )


def _count(aenv: AdoptionEnv, table: str) -> int:
    with sqlite3.connect(aenv.env.store.path) as conn:
        return int(conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0])


def _command_state(aenv: AdoptionEnv, command_id: uuid.UUID) -> str | None:
    with sqlite3.connect(aenv.env.store.path) as conn:
        row = conn.execute(
            "SELECT state FROM commands WHERE command_id = ?", (str(command_id),)
        ).fetchone()
    return None if row is None else str(row[0])


def _spawn(
    mode: str, aenv: AdoptionEnv, signal: Path, request: CatalogAnalysisRequest | None = None
) -> subprocess.Popen[str]:
    args = [sys.executable, "-m", "tests.operations.analysis_worker", mode]
    args += [str(aenv.env.base), str(signal)]
    if request is not None:
        args.append(request.model_dump_json())
    return subprocess.Popen(
        args,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"},
    )


def _await_ready(process: subprocess.Popen[str], signal: Path) -> None:
    ready = signal.with_suffix(".ready")
    deadline = time.monotonic() + 120
    while not ready.exists():
        if process.poll() is not None:
            _, err = process.communicate()
            pytest.fail(f"subprocesso terminou antes do ponto ({process.returncode}): {err}")
        if time.monotonic() > deadline:
            process.kill()
            pytest.fail("subprocesso não alcançou o ponto esperado")
        time.sleep(0.05)


def _finish(process: subprocess.Popen[str]) -> tuple[int, str, str]:
    out, err = process.communicate(timeout=180)
    return process.returncode, out, err


def test_execution_persists_snapshot_enrichment_cache_and_receipt_atomically(
    adopted: tuple[AdoptionEnv, list[AnalysisRun]],
) -> None:
    aenv, (run_a, _) = adopted
    receipt = _execute(aenv, ae.request_for(run_a))

    assert receipt.state == "completed"
    assert receipt.operational.operation == "execute_analysis"
    assert receipt.operational.actor_snapshot.actor_kind == "service"
    assert [r.kind for r in receipt.operational.resulting_refs] == [
        "analysis",
        "diagnostic",
        "enrichment",
    ]
    stored = load_analysis(aenv.env.store, run_a.analysis_id)
    assert stored.run.state == "completed"
    assert stored.receipt == receipt
    assert stored.snapshot is not None
    assert stored.enrichment is not None
    assert stored.snapshot.content_sha256 == receipt.diagnostic_sha256
    assert stored.enrichment.content_sha256 == receipt.enrichment_sha256
    assert stored.snapshot.identity == run_a.identity
    assert receipt.identity_sha256 == run_a.identity.digest()
    assert stored.run.completion is not None
    assert stored.run.completion.receipt_id == receipt.operational.receipt_id
    with_context = [r for r in stored.enrichment.results if r.context_sha256 is not None]
    with aenv.env.store.transaction() as uow:
        cached = uow.cache.scan(analysis_id=str(run_a.analysis_id))
        events = uow.events.list(namespace="operations")
    assert len(cached) == len(with_context) > 0
    by_seq = {seq: document["event"] for seq, document in events}
    assert [by_seq[s] for s in receipt.operational.event_sequence] == [
        "analysis_started",
        "analysis_completed",
    ]
    assert _command_state(aenv, receipt.operational.command_id) == "completed"


def test_replay_and_other_command_on_terminal_run_return_the_original_receipt(
    adopted: tuple[AdoptionEnv, list[AnalysisRun]],
) -> None:
    aenv, (run_a, _) = adopted
    request = ae.request_for(run_a)
    first = _execute(aenv, request)
    snapshots = _count(aenv, "diagnostic_snapshots")

    assert _execute(aenv, request) == first
    other = ae.request_for(run_a)
    assert _execute(aenv, other) == first
    assert _command_state(aenv, other.command_id) is None
    assert _count(aenv, "diagnostic_snapshots") == snapshots == 1


def test_refusals_happen_before_any_effect(
    adopted: tuple[AdoptionEnv, list[AnalysisRun]],
) -> None:
    aenv, (run_a, _) = adopted
    wrong = ae.request_for(run_a).model_copy(update={"expected_identity_sha256": "0" * 64})
    with pytest.raises(OperationalError) as mismatch:
        _execute(aenv, wrong)
    assert mismatch.value.reason == "analysis_identity_mismatch"

    missing = ae.request_for(run_a).model_copy(update={"analysis_id": uuid.uuid4()})
    with pytest.raises(OperationalError) as absent:
        _execute(aenv, missing)
    assert absent.value.reason == "not_found"

    with sqlite3.connect(aenv.env.store.path) as conn:
        curation_key = conn.execute(
            "SELECT command_id FROM commands WHERE namespace = 'curation' LIMIT 1"
        ).fetchone()[0]
    reused = ae.request_for(run_a, uuid.UUID(curation_key))
    with pytest.raises(OperationalError) as conflict:
        _execute(aenv, reused)
    assert conflict.value.reason == "idempotency_conflict"

    assert ae.run_of(aenv, run_a.analysis_id).state == "queued"
    assert _command_state(aenv, wrong.command_id) is None
    assert _count(aenv, "diagnostic_snapshots") == 0


def test_lock_is_exclusive_across_processes_while_store_stays_usable(
    adopted: tuple[AdoptionEnv, list[AnalysisRun]], tmp_path: Path
) -> None:
    aenv, (run_a, _) = adopted
    signal = tmp_path / "liberar"
    holder = _spawn("hold_lock", aenv, signal)
    try:
        _await_ready(holder, signal)
        with pytest.raises(OperationalError) as busy:
            AnalysisCoordinator.acquire(aenv.env.store.root)
        assert busy.value.reason == "coordinator_busy"
        with pytest.raises(OperationalError) as refused:
            _execute(aenv, ae.request_for(run_a))
        assert refused.value.reason == "coordinator_busy"
        assert reanalyze(aenv).queued_analysis_ids
    finally:
        signal.write_text("ok", encoding="utf-8")
    assert _finish(holder)[0] == 0
    with AnalysisCoordinator.acquire(aenv.env.store.root) as coordinator:
        assert coordinator.held
    assert ae.run_of(aenv, run_a.analysis_id).state == "queued"


def test_other_process_reads_and_commands_while_execution_runs(
    adopted: tuple[AdoptionEnv, list[AnalysisRun]], tmp_path: Path
) -> None:
    aenv, (run_a, run_b) = adopted
    request_a = ae.request_for(run_a)
    signal = tmp_path / "continuar"
    worker = _spawn("wait_in_evaluation", aenv, signal, request_a)
    try:
        _await_ready(worker, signal)
        assert ae.run_of(aenv, run_a.analysis_id).state == "running"
        with pytest.raises(OperationalError) as in_progress:
            _execute(aenv, request_a)
        assert in_progress.value.reason == "analysis_in_progress"
        with pytest.raises(OperationalError) as busy:
            _execute(aenv, ae.request_for(run_b))
        assert busy.value.reason == "coordinator_busy"
        assert reanalyze(aenv).queued_analysis_ids
    finally:
        signal.write_text("ok", encoding="utf-8")
    code, out, err = _finish(worker)
    assert code == 0, err
    receipt = CatalogAnalysisReceipt.model_validate_json(out)
    assert receipt.state == "completed"
    assert _execute(aenv, request_a) == receipt
    assert _execute(aenv, ae.request_for(run_b)).state == "completed"


def test_crash_in_evaluation_frees_lock_and_recovery_marks_interrupted(
    adopted: tuple[AdoptionEnv, list[AnalysisRun]], tmp_path: Path
) -> None:
    aenv, (run_a, _) = adopted
    request = ae.request_for(run_a)
    code, _, err = _finish(_spawn("crash_in_evaluation", aenv, tmp_path / "s", request))
    assert code == 9, err
    assert ae.run_of(aenv, run_a.analysis_id).state == "running"
    with pytest.raises(OperationalError) as in_progress:
        _execute(aenv, request)
    assert in_progress.value.reason == "analysis_in_progress"

    with AnalysisCoordinator.acquire(aenv.env.store.root) as coordinator:
        assert coordinator.recover_interrupted_runs(aenv.env.store) == (run_a.analysis_id,)
        assert coordinator.recover_interrupted_runs(aenv.env.store) == ()
    interrupted = ae.run_of(aenv, run_a.analysis_id)
    assert interrupted.state == "interrupted"
    assert [p.code for p in interrupted.problems] == ["executor_interrupted"]
    assert _command_state(aenv, request.command_id) == "abandoned"
    with pytest.raises(OperationalError) as gone:
        _execute(aenv, request)
    assert gone.value.reason == "analysis_interrupted"

    successor_id = next(
        a
        for a in reanalyze(aenv).queued_analysis_ids
        if ae.run_of(aenv, a).identity.pair_id == run_a.identity.pair_id
    )
    successor = ae.run_of(aenv, successor_id)
    assert successor.parent_analysis_id == run_a.analysis_id
    assert _execute(aenv, ae.request_for(successor)).state == "completed"
    assert ae.run_of(aenv, run_a.analysis_id) == interrupted


def test_crash_inside_final_transaction_leaves_no_partial_result(
    adopted: tuple[AdoptionEnv, list[AnalysisRun]], tmp_path: Path
) -> None:
    aenv, (run_a, _) = adopted
    request = ae.request_for(run_a)
    code, _, err = _finish(_spawn("crash_in_final_transaction", aenv, tmp_path / "s", request))
    assert code == 10, err
    for table in ("diagnostic_snapshots", "enrichment_runs", "context_cache"):
        assert _count(aenv, table) == 0
    assert ae.run_of(aenv, run_a.analysis_id).state == "running"
    assert _command_state(aenv, request.command_id) == "in_progress"
    with AnalysisCoordinator.acquire(aenv.env.store.root) as coordinator:
        assert coordinator.recover_interrupted_runs(aenv.env.store) == (run_a.analysis_id,)


def test_crash_after_commit_is_answered_by_replay(
    adopted: tuple[AdoptionEnv, list[AnalysisRun]], tmp_path: Path
) -> None:
    aenv, (run_a, _) = adopted
    request = ae.request_for(run_a)
    code, out, err = _finish(_spawn("crash_after_commit", aenv, tmp_path / "s", request))
    assert (code, out) == (11, ""), err
    stored = load_analysis(aenv.env.store, run_a.analysis_id)
    assert stored.run.state == "completed"
    replayed = _execute(aenv, request)
    assert replayed == stored.receipt
    with AnalysisCoordinator.acquire(aenv.env.store.root) as coordinator:
        assert coordinator.recover_interrupted_runs(aenv.env.store) == ()


def test_divergent_claim_token_blocks_completion(
    adopted: tuple[AdoptionEnv, list[AnalysisRun]], monkeypatch: pytest.MonkeyPatch
) -> None:
    aenv, (run_a, _) = adopted
    original = CatalogEnrichmentService.enrich

    def steal_claim(self: CatalogEnrichmentService, *args: object, **kwargs: object) -> object:
        with aenv.env.store.transaction() as uow:
            row = uow.analyses.get(str(run_a.analysis_id))
            assert row is not None
            document = dict(row.document)
            document["claim"] = {**document["claim"], "execution_token": str(uuid.uuid4())}
            uow.analyses.replace(str(run_a.analysis_id), row.row_version, document)
        return original(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(CatalogEnrichmentService, "enrich", steal_claim)
    request = ae.request_for(run_a)
    with pytest.raises(OperationalError) as conflict:
        _execute(aenv, request)
    assert conflict.value.reason == "execution_claim_conflict"
    assert _count(aenv, "diagnostic_snapshots") == 0
    assert ae.run_of(aenv, run_a.analysis_id).state == "running"
    assert _command_state(aenv, request.command_id) == "in_progress"


def test_recovery_touches_only_orphan_running_runs(
    adopted: tuple[AdoptionEnv, list[AnalysisRun]],
) -> None:
    aenv, (run_a, run_b) = adopted
    _execute(aenv, ae.request_for(run_a))
    with AnalysisCoordinator.acquire(aenv.env.store.root) as coordinator:
        assert coordinator.recover_interrupted_runs(aenv.env.store) == ()
    assert ae.run_of(aenv, run_a.analysis_id).state == "completed"
    assert ae.run_of(aenv, run_b.analysis_id).state == "queued"


def test_recovery_and_execution_require_the_held_lock(
    adopted: tuple[AdoptionEnv, list[AnalysisRun]],
) -> None:
    aenv, _ = adopted
    coordinator = AnalysisCoordinator.acquire(aenv.env.store.root)
    coordinator.close()
    assert not coordinator.held
    with pytest.raises(OperationalError) as released:
        coordinator.recover_interrupted_runs(aenv.env.store)
    assert released.value.reason == "coordinator_busy"


def _forge(aenv: AdoptionEnv, table: str, key: str, value: str, document: dict) -> None:
    payload, digest = encode_document(document)
    with sqlite3.connect(aenv.env.store.path) as conn:
        conn.execute(f"DROP TRIGGER {table}_immutable")
        conn.execute(
            f"UPDATE {table} SET payload = ?, payload_sha256 = ? WHERE {key} = ?",
            (payload, digest, value),
        )


def test_load_analysis_refuses_forged_or_foreign_payloads(
    adopted: tuple[AdoptionEnv, list[AnalysisRun]],
) -> None:
    aenv, (run_a, run_b) = adopted
    receipt_a = _execute(aenv, ae.request_for(run_a))
    receipt_b = _execute(aenv, ae.request_for(run_b))
    stored_b = load_analysis(aenv.env.store, run_b.analysis_id)
    assert stored_b.enrichment is not None

    with aenv.env.store.transaction() as uow:
        foreign = uow.enrichments.get(str(receipt_b.enrichment_id))
        assert foreign is not None
    copied = {**foreign.document, "enrichment_id": str(receipt_a.enrichment_id)}
    _forge(aenv, "enrichment_runs", "enrichment_id", str(receipt_a.enrichment_id), copied)
    with pytest.raises(OperationalError) as foreign_ref:
        load_analysis(aenv.env.store, run_a.analysis_id)
    assert foreign_ref.value.reason == "integrity_error"

    with aenv.env.store.transaction() as uow:
        row = uow.diagnostics.get(str(receipt_b.snapshot_id))
        assert row is not None
    altered = dict(row.document)
    altered["requirements"] = [
        {**r, "state": "compliant", "reason": None} for r in altered["requirements"]
    ]
    _forge(aenv, "diagnostic_snapshots", "snapshot_id", str(receipt_b.snapshot_id), altered)
    with pytest.raises(OperationalError) as forged:
        load_analysis(aenv.env.store, run_b.analysis_id)
    assert forged.value.reason == "integrity_error"


def test_catalog_lost_after_queue_keeps_formal_results_and_fails_only_enrichment(
    adopted: tuple[AdoptionEnv, list[AnalysisRun]],
) -> None:
    aenv, (run_a, _) = adopted
    ref = run_a.identity.catalog_ref
    assert ref is not None
    assert run_a.identity.catalog_state == "available"
    with aenv.env.store.transaction() as uow:
        from src.artifacts.contracts import RetainedCatalogRef

        row = uow.releases.get(ref.catalog_id, ref.version)
        assert row is not None
        retained = RetainedCatalogRef.model_validate(row.document["retained"])
    folder = aenv.env.artifacts.catalog_dir(retained)
    folder.rename(folder.with_name(folder.name + "-afastado"))

    receipt = _execute(aenv, ae.request_for(run_a))
    stored = load_analysis(aenv.env.store, run_a.analysis_id)
    assert receipt.state == "completed"
    assert receipt.catalog_runtime_state == "unavailable"
    assert stored.snapshot is not None
    assert stored.enrichment is not None
    assert stored.snapshot.identity.catalog_state == "available"
    assert [r.state for r in stored.snapshot.requirements] == ["non_compliant"] * 4
    assert {(r.status, r.reason) for r in stored.enrichment.results} == {
        ("failed", "package_error")
    }
    assert "catalog_unavailable" in {p.code for p in stored.run.problems}


@pytest.mark.parametrize("where", ["memory", "disk"])
def test_source_mutated_during_evaluation_fails_the_whole_run(
    adopted: tuple[AdoptionEnv, list[AnalysisRun]],
    monkeypatch: pytest.MonkeyPatch,
    where: str,
) -> None:
    aenv, (run_a, _) = adopted
    original = CatalogEnrichmentService.enrich

    def mutate(self: CatalogEnrichmentService, snapshot: object, **kwargs: object) -> object:
        if where == "memory":
            session = kwargs["observations"]._session  # type: ignore[attr-defined]
            session.backend_model().create_entity("IfcWall", GlobalId="0" * 22)
        else:
            path = aenv.env.artifacts.read_verified_source(run_a.identity.ifc)
            os.chmod(path, 0o644)
            with path.open("ab") as handle:
                handle.write(b"/* mutado */\n")
        return original(self, snapshot, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(CatalogEnrichmentService, "enrich", mutate)
    receipt = _execute(aenv, ae.request_for(run_a))
    assert (receipt.state, [p.code for p in receipt.problems]) == ("failed", ["source_mutated"]), (
        receipt.problems
    )
    assert _count(aenv, "diagnostic_snapshots") == 0
    assert _count(aenv, "context_cache") == 0


def test_first_analysis_without_catalog_completes_without_false_failures(
    tmp_path: Path,
) -> None:
    from src.operations.analysis_queue import AnalysisQueueService, initial_analysis_command
    from src.validation.analysis_identity import current_execution_profile

    aenv = ae.make_analysis_env(tmp_path / "env")
    state = aenv.projects.load_project_state(aenv.project_id)
    pair = next(p for p in state.pairs if p.pair_id == aenv.pairs[0])
    profile = current_execution_profile()
    queued = AnalysisQueueService(aenv.env.store, aenv.env.artifacts).queue_initial_analysis(
        command=initial_analysis_command(
            uuid.uuid4(),
            aenv.human,
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
    run = ae.run_of(aenv, queued.queued_analysis_ids[0])
    assert run.identity.catalog_state == "not_attached"

    receipt = _execute(aenv, ae.request_for(run))

    assert (receipt.state, receipt.catalog_runtime_state, receipt.problems) == (
        "completed",
        "not_attached",
        (),
    )
    assert receipt.field_counts == {"abstained": 4}
    stored = load_analysis(aenv.env.store, run.analysis_id)
    assert stored.enrichment is not None
    assert {(r.status, r.reason) for r in stored.enrichment.results} == {
        ("abstained", "insufficient_context")
    }


def test_condition_identity_covers_m3_code_and_operation_manifest(tmp_path: Path) -> None:
    """E3-05: código M3 e manifesto do bundle fazem parte da condição congelada."""
    import shutil

    from src.validation import analysis_identity as ai

    assert set(ai.M3_MODULES) >= {
        f"src/suggestion_engine/catalog_{name}.py"
        for name in ("cache", "context", "contracts", "evidence", "operations", "service")
    }
    for name in ai.M3_MODULES:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, tmp_path / name)
    assert ai.m3_code_sha256(tmp_path) == ai.m3_code_sha256(ROOT)
    changed = tmp_path / "src/suggestion_engine/catalog_operations.py"
    changed.write_bytes(changed.read_bytes() + b"\n# alterado\n")
    assert ai.m3_code_sha256(tmp_path) != ai.m3_code_sha256(ROOT)

    profile = ai.current_execution_profile()
    limits = profile.limits
    verifier = profile.verifier
    base = ai.condition_config_sha256(
        limits, verifier.capability_manifest_sha256, verifier.options_sha256
    )
    assert base == profile.condition_config_sha256
    other = ai.condition_config_sha256(
        limits,
        verifier.capability_manifest_sha256,
        verifier.options_sha256,
        operation_manifest="0" * 64,
    )
    assert other != base


def test_executor_refuses_a_bundle_other_than_the_condition_before_claim(
    adopted: tuple[AdoptionEnv, list[AnalysisRun]],
) -> None:
    """E3-05: bundle diferente do congelado na condição é recusado sem efeito."""
    from src.suggestion_engine.catalog_operations import E3_SPECS, E3OperationBundle

    aenv, (run_a, _) = adopted
    full = ae.operation_bundle()
    key = ("recover_exact_property", "1.0.0")
    partial = E3OperationBundle.create(
        tuple(s for s in E3_SPECS if (s.operation_id, s.version) == key),
        {key: full.handlers[key]},
    )
    request = ae.request_for(run_a)
    with pytest.raises(OperationalError) as refused:
        run_catalog_analysis(
            request,
            store=aenv.env.store,
            artifacts=aenv.env.artifacts,
            operation_bundle=partial,
        )
    assert refused.value.reason == "execution_profile_mismatch"
    assert ae.run_of(aenv, run_a.analysis_id).state == "queued"
    assert _command_state(aenv, request.command_id) is None


@pytest.mark.parametrize(
    "limits",
    [{"max_selectors_per_field": 1}, {"max_context_bytes": 1}],
    ids=["selectors", "context_bytes"],
)
def test_frozen_limits_reach_the_executed_recipe(tmp_path: Path, limits: dict) -> None:
    """E3-07: limites admitidos no pin valem no M3 do pipeline público; nada é proposto."""
    from src.suggestion_engine.catalog_contracts import recipe_for
    from src.suggestion_engine.catalog_operations import build_e3_operation_bundle
    from src.validation.analysis_identity import ExecutionLimits, current_execution_profile
    from tests.operations.adoption_env import add_pair, make_adoption_env, release_dir
    from tests.suggestion_engine import m3_helpers as m
    from tests.validation import ids_builders as x
    from tests.validation import ifc_builders as ib

    aenv = make_adoption_env(tmp_path / "env", pairs=0)
    model = ib.model()
    m.slab(model, ("SYN_Legado", "Metodo", " A ", "IfcLabel"))
    add_pair(
        aenv,
        "synthetic",
        ifc=model.to_string().encode(),
        ids=x.ids(x.spec("S", x.entity("IFCSLAB"), m.TARGET)),
    )
    published = publish_first(aenv.env, ae.as_draft(m.content(codes=("A",))))
    state = aenv.projects.load_project_state(aenv.project_id)
    frozen = ExecutionLimits(**limits)
    plan = aenv.adoption.prepare_catalog_adoption(
        project_id=aenv.project_id,
        expected_pin_revision=state.pin_revision,
        expected_pair_set_revision=state.pair_set_revision,
        target_ref=published.release,
        target_dir=release_dir(aenv, published.release),
        intent="initial",
        reason="limites congelados",
        execution_profile=current_execution_profile(frozen),
        prepared_by_actor_context_id=aenv.human,
    )
    queued = ae.run_of(aenv, apply(aenv, plan).queued_analysis_ids[0])
    receipt = run_catalog_analysis(
        ae.request_for(queued),
        store=aenv.env.store,
        artifacts=aenv.env.artifacts,
        operation_bundle=build_e3_operation_bundle(),
    )
    stored = load_analysis(aenv.env.store, receipt.analysis_id)
    assert stored.run.identity.limits == frozen
    assert stored.enrichment is not None
    assert stored.enrichment.identity.recipe_sha256 == recipe_for(frozen).digest()
    (result,) = stored.enrichment.results
    assert result.status != "proposed"
    assert result.reason == "context_limit_exceeded"


def test_retained_ids_changed_during_enrichment_fails_the_run(
    adopted: tuple[AdoptionEnv, list[AnalysisRun]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """E3-11: o IDS retido é reconferido ao concluir, como o IFC; nada é persistido."""
    aenv, (run_a, _) = adopted
    original = CatalogEnrichmentService.enrich

    def mutate(self: CatalogEnrichmentService, snapshot: object, **kwargs: object) -> object:
        result = original(self, snapshot, **kwargs)  # type: ignore[arg-type]
        path = aenv.env.artifacts.read_verified_source(run_a.identity.ids)
        os.chmod(path, 0o644)
        with path.open("ab") as handle:
            handle.write(b"<!-- adulterado -->\n")
        return result

    monkeypatch.setattr(CatalogEnrichmentService, "enrich", mutate)
    receipt = _execute(aenv, ae.request_for(run_a))
    assert (receipt.state, [p.code for p in receipt.problems]) == (
        "failed",
        ["artifact_integrity_error"],
    ), receipt.problems
    assert receipt.snapshot_id is None
    assert _count(aenv, "diagnostic_snapshots") == 0
    assert _count(aenv, "context_cache") == 0


def test_code_identity_ignores_line_endings_only(tmp_path: Path) -> None:
    """M-07: CRLF/LF do mesmo código (normalização do .gitattributes) não muda a condição."""
    from src.validation import analysis_identity as ai

    for name in (*ai.M3_MODULES, *ai.VERIFIER_MODULES):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        data = (ROOT / name).read_bytes().replace(b"\r\n", b"\n")
        target.write_bytes(data.replace(b"\n", b"\r\n"))
    assert ai.m3_code_sha256(tmp_path) == ai.m3_code_sha256(ROOT)
    assert ai.code_sha256(tmp_path) == ai.code_sha256(ROOT)
