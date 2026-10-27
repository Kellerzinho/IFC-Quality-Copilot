"""Porta E2 ``CurationStore`` sobre a autoridade operacional real e índice global de comandos.

Os testes de contrato da E2 são reexecutados contra ``SQLiteCurationStore`` (a
fábrica ``make_store`` deste módulo substitui a do módulo original). Atores são
SINTÉTICOS declarados; nada aqui é aprovação real de conteúdo.
"""

import uuid
from collections.abc import Callable
from pathlib import Path

import pytest

from src.domain_catalog.actor import snapshot_actor
from src.domain_catalog.curation_errors import (
    ActorContextError,
    IdempotencyConflictError,
)
from src.domain_catalog.curation_models import CommandMeta
from src.domain_catalog.draft_store import CurationStore, StoreConflictError
from src.operations.actor_context import ActorContextService, LocalActorContext
from src.operations.contracts import OperationalError
from src.operations.curation_adapter import SQLiteCurationStore
from src.operations.database import OperationalStore
from tests.domain_catalog import factories as f
from tests.domain_catalog.test_curation_store_contract import (  # noqa: F401
    test_committed_records_and_events_survive_reopening,
    test_documents_are_copies_that_cannot_change_the_store,
    test_events_keep_commit_order_with_increasing_sequence,
    test_failure_inside_a_transaction_discards_every_write,
    test_inserted_record_is_read_back_with_version_one,
    test_inserting_an_existing_key_is_a_conflict,
    test_non_json_document_is_refused_without_partial_write,
    test_replace_requires_the_expected_version,
    test_replacing_a_missing_record_is_a_conflict,
    test_scan_lists_records_of_one_kind_in_key_order,
    test_transactions_that_read_then_write_never_interleave,
)

SYNTHETIC_HUMAN = "Pessoa Sintética Declarada (teste)"


@pytest.fixture
def make_store() -> Callable[[Path], CurationStore]:
    """Fábrica do adaptador real; nova instância sobre a mesma pasta simula reinício."""

    def factory(base: Path) -> CurationStore:
        return SQLiteCurationStore(OperationalStore.open(base, purpose="synthetic_test"))

    return factory


def _setup(tmp_path: Path) -> tuple[OperationalStore, SQLiteCurationStore, ActorContextService]:
    store = OperationalStore.open(tmp_path / "db", purpose="synthetic_test")
    return store, SQLiteCurationStore(store), ActorContextService(store)


def test_real_adapter_declares_durable_backend(tmp_path: Path) -> None:
    _, curation, _ = _setup(tmp_path)
    assert curation.operational is True


def test_actor_context_is_persisted_and_resolved_by_e2_snapshot(tmp_path: Path) -> None:
    store, _, actors = _setup(tmp_path)
    created = actors.register(actor_kind="human", declared_name=SYNTHETIC_HUMAN)
    resolved = ActorContextService(OperationalStore.open(tmp_path / "db")).resolve(
        created.actor_context_id
    )

    assert isinstance(resolved, LocalActorContext)
    assert resolved == created
    snapshot = snapshot_actor(resolved)
    assert snapshot.identity_assurance == "unverified_local"
    assert snapshot.installation_id == store.installation_id
    assert actors.resolve(str(uuid.uuid4())) is None


def test_actor_requirements_never_authenticate_or_promote(tmp_path: Path) -> None:
    _, _, actors = _setup(tmp_path)
    human = actors.register(actor_kind="human", declared_name=SYNTHETIC_HUMAN)
    assistant = actors.register(actor_kind="assistant", declared_name=None)

    assert actors.require(human.actor_context_id, requirement="human").actor_kind == "human"
    with pytest.raises(OperationalError) as refused:
        actors.require(assistant.actor_context_id, requirement="human")
    assert refused.value.reason == "human_actor_required"
    with pytest.raises(OperationalError) as unknown:
        actors.require(str(uuid.uuid4()), requirement="any")
    assert unknown.value.reason == "invalid_actor"
    with pytest.raises(ValueError):
        actors.register(actor_kind="human", declared_name="   ")


def test_actor_from_other_installation_is_incoherent(tmp_path: Path) -> None:
    store, _, actors = _setup(tmp_path)
    created = actors.register(actor_kind="human", declared_name=SYNTHETIC_HUMAN)
    forged = created.model_copy(update={"installation_id": "outra-instalacao"})
    import sqlite3

    from src.operations.repositories import encode_document

    payload, digest = encode_document(forged.model_dump(mode="json"))
    with sqlite3.connect(store.path) as conn:
        conn.execute("DROP TRIGGER actor_contexts_immutable")
        conn.execute(
            "UPDATE actor_contexts SET installation_id = ?, payload = ?, payload_sha256 = ?",
            ("outra-instalacao", payload, digest),
        )
    with pytest.raises(ActorContextError):
        actors.resolve(created.actor_context_id)


def _record(command_id: str, actor: str, state: str = "completed") -> dict[str, object]:
    receipt = {
        "command_id": command_id,
        "operation": "request_change",
        "subject_kind": "request",
        "subject_id": "r",
        "event_seqs": [1],
        "committed_at": "2026-10-22T00:00:00Z",
        "store_operational": True,
    }
    done = state == "completed"
    return {
        "command_id": command_id,
        "operation": "request_change",
        "payload_sha256": "a" * 64,
        "actor_context_id": actor,
        "state": state,
        "recorded_at": "2026-10-22T00:00:00Z",
        "receipt": receipt if done else None,
        "result": {"ok": True} if done else None,
        "intent_id": None,
    }


def test_e2_command_reserves_global_index_in_same_transaction(tmp_path: Path) -> None:
    store, curation, actors = _setup(tmp_path)
    actor = actors.register(actor_kind="human", declared_name=SYNTHETIC_HUMAN).actor_context_id
    key = str(uuid.uuid4())
    with curation.transaction() as tx:
        tx.insert("command", key, _record(key, actor))
    with store.transaction() as uow:
        row = uow.commands.get(key)
    assert row is not None
    assert (row.namespace, row.operation, row.state) == ("curation", "request_change", "completed")
    with pytest.raises(IdempotencyConflictError), store.transaction() as uow:
        uow.commands.reserve(
            command_id=key,
            namespace="operations",
            operation="create_project",
            payload_sha256="a" * 64,
            actor_context_id=actor,
            record_ref=f"operations/{key}",
        )


def test_e3_reserved_key_is_conflict_for_e2_lookup(tmp_path: Path) -> None:
    store, curation, actors = _setup(tmp_path)
    actor = actors.register(actor_kind="human", declared_name=SYNTHETIC_HUMAN).actor_context_id
    key = str(uuid.uuid4())
    with store.transaction() as uow:
        uow.commands.reserve(
            command_id=key,
            namespace="operations",
            operation="create_project",
            payload_sha256="a" * 64,
            actor_context_id=actor,
            record_ref=f"operations/{key}",
        )
    with pytest.raises(IdempotencyConflictError), curation.transaction() as tx:
        tx.get("command", key)
    with pytest.raises(IdempotencyConflictError), curation.transaction() as tx:
        tx.insert("command", key, _record(key, actor))


def test_e2_in_progress_key_cannot_be_taken_and_state_change_keeps_identity(
    tmp_path: Path,
) -> None:
    store, curation, actors = _setup(tmp_path)
    actor = actors.register(actor_kind="human", declared_name=SYNTHETIC_HUMAN).actor_context_id
    key = str(uuid.uuid4())
    with curation.transaction() as tx:
        tx.insert("command", key, _record(key, actor, state="in_progress"))
    with pytest.raises(IdempotencyConflictError), store.transaction() as uow:
        uow.commands.reserve(
            command_id=key,
            namespace="operations",
            operation="request_change",
            payload_sha256="a" * 64,
            actor_context_id=actor,
            record_ref=f"curation_records/command/{key}",
        )
    changed = {**_record(key, actor), "payload_sha256": "b" * 64}
    with pytest.raises(IdempotencyConflictError), curation.transaction() as tx:
        tx.replace("command", key, 1, changed)
    with curation.transaction() as tx:
        tx.replace("command", key, 1, _record(key, actor))
    with store.transaction() as uow:
        row = uow.commands.get(key)
    assert row is not None
    assert row.state == "completed"


def test_failure_rolls_back_curation_record_and_index_reservation(tmp_path: Path) -> None:
    store, curation, actors = _setup(tmp_path)
    actor = actors.register(actor_kind="human", declared_name=SYNTHETIC_HUMAN).actor_context_id
    key = str(uuid.uuid4())

    def interrupted() -> None:
        with curation.transaction() as tx:
            tx.insert("command", key, _record(key, actor))
            tx.append_event({"tipo": "x"})
            raise RuntimeError("falha injetada antes do commit")

    with pytest.raises(RuntimeError, match="injetada"):
        interrupted()
    reopened = SQLiteCurationStore(OperationalStore.open(tmp_path / "db"))
    with reopened.transaction() as tx:
        assert tx.get("command", key) is None
        assert tx.events() == ()
    with store.transaction() as uow:
        assert uow.commands.get(key) is None
        remaining = uow.events.list()
    assert [document["event"] for _, document in remaining] == ["actor_context_registered"]


def test_unknown_actor_in_e2_command_is_refused_by_foreign_key(tmp_path: Path) -> None:
    _, curation, _ = _setup(tmp_path)
    key = str(uuid.uuid4())
    with pytest.raises(StoreConflictError), curation.transaction() as tx:
        tx.insert("command", key, _record(key, str(uuid.uuid4())))


def test_curation_service_replay_over_real_store_survives_reopen(tmp_path: Path) -> None:
    from src.domain_catalog.curation import CurationService

    store, curation, actors = _setup(tmp_path)
    importer = actors.register(actor_kind="service", declared_name=None).actor_context_id
    meta = CommandMeta(command_id=str(uuid.uuid4()), actor_context_id=importer)
    service = CurationService(curation, actors)
    first = service.import_draft(
        meta,
        title="Proposta sintética",
        catalog=f.catalog_identity(),
        content=f.minimal_content("draft"),
        source_label="fixture sintética",
        reason="teste de autoridade real",
    )
    reopened_store = OperationalStore.open(tmp_path / "db")
    again = CurationService(
        SQLiteCurationStore(reopened_store), ActorContextService(reopened_store)
    ).import_draft(
        meta,
        title="Proposta sintética",
        catalog=f.catalog_identity(),
        content=f.minimal_content("draft"),
        source_label="fixture sintética",
        reason="teste de autoridade real",
    )

    assert first.replayed is False
    assert again.replayed is True
    assert again.receipt == first.receipt
    assert first.receipt.store_operational is True
    with store.transaction() as uow:
        row = uow.commands.get(meta.command_id)
    assert row is not None
    assert (row.namespace, row.state) == ("curation", "completed")
