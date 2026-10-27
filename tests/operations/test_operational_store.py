"""Autoridade SQLite real: migração, pragmas, CAS, integridade, rollback e índice de comandos.

Reescrito em 22/10/2026 a partir do arquivo RED do executor anterior (SHA-256
8c42dfcc…, preservado no dossier e3-integral-implementacao-medium-2026-10-22): o
esquema agora tem colunas de identidade, FKs e unicidade no banco (plano §3.1), e
cada comportamento do teste original continua verificado.
"""

import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from src.domain_catalog.curation_errors import IdempotencyConflictError
from src.domain_catalog.draft_store import StoreConflictError, StoreError
from src.operations.database import (
    OperationalStore,
    StoreBusyError,
    StoreIntegrityError,
    StorePurposeError,
    StoreSchemaError,
)

ROOT = Path(__file__).resolve().parents[2]
P1 = "1111aaaa-1111-4111-8111-111111111111"
P2 = "1111bbbb-1111-4111-8111-111111111111"
M1 = "2222aaaa-2222-4222-8222-222222222222"
S1 = "3333aaaa-3333-4333-8333-333333333333"
ACTOR = "4444aaaa-4444-4444-8444-444444444444"
SHA = "c" * 64


def _store(root: Path, purpose: str | None = "synthetic_test") -> OperationalStore:
    return OperationalStore.open(root, purpose=purpose)  # type: ignore[arg-type]


def _project(project_id: str = P1, revision: int = 0, **extra: Any) -> dict[str, Any]:
    return {"project_id": project_id, "pair_set_revision": revision, "name": "Obra", **extra}


def _actor() -> dict[str, Any]:
    return {
        "actor_context_id": ACTOR,
        "actor_kind": "human",
        "installation_id": "inst",
        "session_id": "sess",
    }


def _source(revision: int = 1, project_id: str = P1, model_id: str = M1) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "model_id": model_id,
        "source_id": S1,
        "revision": revision,
        "role": "ifc",
        "sha256": SHA,
        "size_bytes": 5,
        "storage_key": f"s/ifc/{SHA}",
    }


def test_new_store_requires_purpose_and_records_it(tmp_path: Path) -> None:
    with pytest.raises(StorePurposeError, match="purpose"):
        OperationalStore.open(tmp_path / "a")
    store = _store(tmp_path / "b")
    reopened = OperationalStore.open(tmp_path / "b")

    assert (store.purpose, reopened.purpose) == ("synthetic_test", "synthetic_test")
    assert store.installation_id == reopened.installation_id
    assert store.schema_version == 1


def test_purpose_is_immutable_and_future_schema_is_refused(tmp_path: Path) -> None:
    _store(tmp_path)
    with pytest.raises(StorePurposeError, match="purpose"):
        OperationalStore.open(tmp_path, purpose="operational")
    with sqlite3.connect(tmp_path / "operations.sqlite3") as conn:
        conn.execute("PRAGMA user_version=999")
    with pytest.raises(StoreSchemaError, match="schema"):
        OperationalStore.open(tmp_path)


def test_connection_pragmas_are_durable_and_bounded(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with store.transaction() as tx:
        assert tx.connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert tx.connection.execute("PRAGMA synchronous").fetchone()[0] == 2
        assert tx.connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert tx.connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        assert tx.connection.in_transaction


def test_committed_state_reopens_in_another_process(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with store.transaction() as tx:
        tx.projects.insert(_project(typed=[False, 0, "0", None]))
        seq = tx.events.append("operations", {"event": "created"})
    script = (
        "import json, sys; from pathlib import Path\n"
        "from src.operations.database import OperationalStore\n"
        "s = OperationalStore.open(Path(sys.argv[1]))\n"
        "with s.transaction() as tx:\n"
        f"    row = tx.projects.get('{P1}')\n"
        "    print(json.dumps({'doc': row.document, 'events': tx.events.list(), "
        "'purpose': s.purpose}))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    loaded = json.loads(result.stdout)

    assert loaded["doc"]["typed"] == [False, 0, "0", None]
    assert loaded["events"] == [[seq, {"event": "created"}]]
    assert loaded["purpose"] == "synthetic_test"


@pytest.mark.parametrize(
    "tamper",
    [
        "UPDATE projects SET payload = '{\"bad\":true}' WHERE project_id = ?",
        "UPDATE projects SET pair_set_revision = 7 WHERE project_id = ?",
    ],
)
def test_tampered_payload_or_identity_column_is_integrity_error(
    tmp_path: Path, tamper: str
) -> None:
    store = _store(tmp_path)
    with store.transaction() as tx:
        tx.projects.insert(_project())
    with sqlite3.connect(tmp_path / "operations.sqlite3") as conn:
        conn.execute(tamper, (P1,))

    with pytest.raises(StoreIntegrityError, match="integrity"), store.transaction() as tx:
        tx.projects.get(P1)


def test_failure_discards_record_event_and_command_reservation(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with store.transaction() as tx:
        tx.actors.insert(_actor())

    def interrupted() -> None:
        with store.transaction() as tx:
            tx.projects.insert(_project())
            tx.commands.reserve(
                command_id="cmd-0001",
                namespace="operations",
                operation="create_project",
                payload_sha256="a" * 64,
                actor_context_id=ACTOR,
                record_ref="operations/create_project",
            )
            tx.events.append("operations", {"event": "created"})
            raise RuntimeError("injected")

    with pytest.raises(RuntimeError, match="injected"):
        interrupted()
    with store.transaction() as tx:
        assert tx.projects.get(P1) is None
        assert tx.commands.get("cmd-0001") is None
        assert tx.events.list() == ()


def test_foreign_keys_are_enforced_by_the_database(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with pytest.raises(StoreConflictError), store.transaction() as tx:
        tx.models.insert({"model_id": M1, "project_id": P1, "discipline": "arquitetura"})
    with store.transaction() as tx:
        tx.projects.insert(_project())
        tx.models.insert({"model_id": M1, "project_id": P1, "discipline": "arquitetura"})
        tx.sources.insert_revision(_source())
    with pytest.raises(StoreConflictError), store.transaction() as tx:
        tx.sources.insert_revision(
            _source(revision=2, model_id="2222bbbb-2222-4222-8222-222222222222")
        )


def test_immutable_rows_cannot_be_updated_or_deleted_even_by_raw_sql(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with store.transaction() as tx:
        tx.projects.insert(_project())
        tx.models.insert({"model_id": M1, "project_id": P1, "discipline": "arquitetura"})
        tx.sources.insert_revision(_source())
        tx.events.append("operations", {"n": 1})
    for statement in (
        "UPDATE models SET payload = payload",
        "DELETE FROM models",
        "UPDATE source_revisions SET size_bytes = 6",
        "DELETE FROM events",
        "UPDATE events SET namespace = 'curation'",
        "DELETE FROM projects",
    ):
        with pytest.raises(sqlite3.IntegrityError), store.transaction() as tx:
            tx.connection.execute(statement)


def test_cas_between_two_connections_never_overwrites(tmp_path: Path) -> None:
    first, second = _store(tmp_path), OperationalStore.open(tmp_path)
    with first.transaction() as tx:
        tx.projects.insert(_project())
    with second.transaction() as tx:
        assert tx.projects.replace(P1, 1, _project(revision=1)).row_version == 2
    with pytest.raises(StoreConflictError), first.transaction() as tx:
        tx.projects.replace(P1, 1, _project(revision=2))
    with pytest.raises(StoreConflictError), first.transaction() as tx:
        tx.projects.insert(_project(revision=9))
    with pytest.raises(StoreConflictError), first.transaction() as tx:
        tx.projects.replace(P1, 2, _project(project_id=P2, revision=2))
    with first.transaction() as tx:
        current = tx.projects.get(P1)
    assert current is not None
    assert (current.row_version, current.document["pair_set_revision"]) == (2, 1)


def test_concurrent_writers_serialize_read_then_write(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with store.transaction() as tx:
        tx.projects.insert(_project())
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def bump() -> None:
        barrier.wait()
        try:
            with store.transaction() as tx:
                row = tx.projects.get(P1)
                assert row is not None
                time.sleep(0.05)
                tx.projects.replace(
                    P1,
                    row.row_version,
                    _project(revision=row.document["pair_set_revision"] + 1),
                )
            outcomes.append("ok")
        except StoreError as exc:
            outcomes.append(exc.code)

    threads = [threading.Thread(target=bump) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    with store.transaction() as tx:
        final = tx.projects.get(P1)

    assert final is not None
    assert final.document["pair_set_revision"] == outcomes.count("ok")
    assert final.row_version == 1 + outcomes.count("ok")


def test_lock_held_elsewhere_is_store_busy_not_infinite_retry(tmp_path: Path) -> None:
    store = OperationalStore.open(tmp_path, purpose="synthetic_test", busy_timeout_ms=100)
    blocker = sqlite3.connect(tmp_path / "operations.sqlite3", isolation_level=None)
    blocker.execute("BEGIN IMMEDIATE")
    try:
        started = time.monotonic()
        with pytest.raises(StoreBusyError), store.transaction():
            pass
        assert time.monotonic() - started < 5
    finally:
        blocker.execute("ROLLBACK")
        blocker.close()


@pytest.mark.parametrize(
    ("first", "second"), [("curation", "operations"), ("operations", "curation")]
)
def test_command_index_is_global_with_exact_replay(tmp_path: Path, first: str, second: str) -> None:
    store = _store(tmp_path)
    identity: dict[str, Any] = {
        "command_id": "cmd-0001",
        "namespace": first,
        "operation": "op",
        "payload_sha256": "a" * 64,
        "actor_context_id": ACTOR,
        "record_ref": "ref",
    }
    with store.transaction() as tx:
        tx.actors.insert(_actor())
        original = tx.commands.reserve(**identity)
    with store.transaction() as tx:
        assert tx.commands.reserve(**identity) == original
    for change in (
        {"namespace": second},
        {"operation": "other"},
        {"payload_sha256": "b" * 64},
        {"record_ref": "outra"},
    ):
        with pytest.raises(IdempotencyConflictError), store.transaction() as tx:
            tx.commands.reserve(**{**identity, **change})
    with pytest.raises(StoreConflictError), store.transaction() as tx:
        tx.commands.reserve(**{**identity, "command_id": "cmd-0002", "actor_context_id": "x"})


def test_command_completion_keeps_identity_and_terminal_state(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with store.transaction() as tx:
        tx.actors.insert(_actor())
        tx.commands.reserve(
            command_id="cmd-0001",
            namespace="operations",
            operation="op",
            payload_sha256="a" * 64,
            actor_context_id=ACTOR,
            record_ref="ref",
        )
        tx.commands.complete("cmd-0001", {"receipt": 1})
    with store.transaction() as tx:
        row = tx.commands.get("cmd-0001")
        assert row is not None
        assert (row.state, row.receipt) == ("completed", {"receipt": 1})
    with pytest.raises(StoreConflictError), store.transaction() as tx:
        tx.commands.complete("cmd-0001", {"receipt": 2})
    with pytest.raises(sqlite3.IntegrityError), store.transaction() as tx:
        tx.connection.execute("UPDATE commands SET operation = 'x'")


def test_release_identity_is_unique_per_catalog_version(tmp_path: Path) -> None:
    store = _store(tmp_path)
    ref = {"catalog_id": "urn:uuid:00000000-0000-4000-8000-0000000000e1", "version": "1.0.0"}
    record = {"catalog": {**ref, "manifest_sha256": "d" * 64}, "storage_key": "r/x"}
    with store.transaction() as tx:
        assert tx.releases.insert_or_verify(record).document == record
    with store.transaction() as tx:
        assert tx.releases.insert_or_verify(record).document == record
    collision = {"catalog": {**ref, "manifest_sha256": "e" * 64}, "storage_key": "r/y"}
    with (
        pytest.raises(StoreConflictError, match="version_hash_collision"),
        store.transaction() as tx,
    ):
        tx.releases.insert_or_verify(collision)


def test_events_have_global_sequence_and_namespace_filter(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with store.transaction() as tx:
        a = tx.events.append("operations", {"n": 1})
        b = tx.events.append("curation", {"n": 2})
        c = tx.events.append("operations", {"n": 3})
    with store.transaction() as tx:
        assert [s for s, _ in tx.events.list()] == [a, b, c]
        assert tx.events.list(namespace="curation") == ((b, {"n": 2}),)
        assert tx.events.list(after_seq=a, namespace="operations") == ((c, {"n": 3}),)
    assert a < b < c
    with pytest.raises(ValueError), store.transaction() as tx:
        tx.events.append("outro", {"n": 4})


def test_non_json_payload_is_refused_without_partial_write(tmp_path: Path) -> None:
    store = _store(tmp_path)

    def partial() -> None:
        with store.transaction() as tx:
            tx.projects.insert(_project())
            tx.events.append("operations", {"x": float("nan")})

    with pytest.raises(StoreError, match="JSON"):
        partial()
    with store.transaction() as tx:
        assert tx.projects.get(P1) is None
