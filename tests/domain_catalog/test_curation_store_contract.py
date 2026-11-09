"""Contrato da porta de persistência da curadoria (``CurationStore``).

A suíte vale para qualquer adaptador: hoje só existe o ADAPTADOR DE TESTE
(``curation_adapters.SqliteTestCurationStore``, não operacional); o adaptador do M6,
quando existir, deve passar por ela. Verifica o que o serviço de curadoria pressupõe:
leitura de cópias, inserção única, troca com revisão esperada, transação que desfaz
tudo em falha, transações que não se intercalam, eventos em ordem e dados que
sobrevivem à reabertura.
"""

import threading
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from src.domain_catalog.draft_store import (
    CurationStore,
    CurationTransaction,
    StoreConflictError,
    StoreError,
    StoreUnavailableError,
)
from tests.domain_catalog.curation_adapters import SqliteTestCurationStore

StoreFactory = Callable[[Path], CurationStore]


def _in_transaction(store: CurationStore, writes: Callable[[CurationTransaction], None]) -> None:
    """Executa as escritas numa transação (a exceção, se houver, sai da transação)."""
    with store.transaction() as tx:
        writes(tx)


@pytest.fixture(params=["sqlite-teste"])
def make_store(request: pytest.FixtureRequest) -> StoreFactory:
    """Fábrica de adaptadores; um novo adaptador sobre a mesma pasta simula reinício."""
    if request.param == "sqlite-teste":
        return lambda base: SqliteTestCurationStore(base / "curadoria-teste.sqlite3")
    raise AssertionError(request.param)


def test_test_adapter_declares_itself_non_operational(tmp_path: Path) -> None:
    assert SqliteTestCurationStore(tmp_path / "s.sqlite3").operational is False


def test_inserted_record_is_read_back_with_version_one(
    tmp_path: Path, make_store: StoreFactory
) -> None:
    store = make_store(tmp_path)
    with store.transaction() as tx:
        stored = tx.insert("request", "r-1", {"a": 1, "b": [True, None, "ç"]})
    with store.transaction() as tx:
        loaded = tx.get("request", "r-1")

    assert stored.version == 1
    assert loaded is not None
    assert loaded.version == 1
    assert loaded.document == {"a": 1, "b": [True, None, "ç"]}


def test_documents_are_copies_that_cannot_change_the_store(
    tmp_path: Path, make_store: StoreFactory
) -> None:
    store = make_store(tmp_path)
    original = {"lista": [1, 2]}
    with store.transaction() as tx:
        tx.insert("request", "r-1", original)
    original["lista"].append(3)
    with store.transaction() as tx:
        loaded = tx.get("request", "r-1")
        assert loaded is not None
        loaded.document["lista"].append(4)
    with store.transaction() as tx:
        again = tx.get("request", "r-1")

    assert again is not None
    assert again.document == {"lista": [1, 2]}


def test_inserting_an_existing_key_is_a_conflict(tmp_path: Path, make_store: StoreFactory) -> None:
    store = make_store(tmp_path)
    with store.transaction() as tx:
        tx.insert("draft", "d-1", {"v": 1})

    with pytest.raises(StoreConflictError), store.transaction() as tx:
        tx.insert("draft", "d-1", {"v": 2})


def test_replace_requires_the_expected_version(tmp_path: Path, make_store: StoreFactory) -> None:
    store = make_store(tmp_path)
    with store.transaction() as tx:
        tx.insert("draft", "d-1", {"v": 1})
    with store.transaction() as tx:
        replaced = tx.replace("draft", "d-1", 1, {"v": 2})

    with pytest.raises(StoreConflictError), store.transaction() as tx:
        tx.replace("draft", "d-1", 1, {"v": 3})
    with store.transaction() as tx:
        current = tx.get("draft", "d-1")

    assert replaced.version == 2
    assert current is not None
    assert (current.version, current.document) == (2, {"v": 2})


def test_replacing_a_missing_record_is_a_conflict(tmp_path: Path, make_store: StoreFactory) -> None:
    store = make_store(tmp_path)
    with pytest.raises(StoreConflictError), store.transaction() as tx:
        tx.replace("draft", "inexistente", 1, {"v": 1})


def test_failure_inside_a_transaction_discards_every_write(
    tmp_path: Path, make_store: StoreFactory
) -> None:
    store = make_store(tmp_path)
    with store.transaction() as tx:
        tx.insert("draft", "d-1", {"v": 1})

    def interrupted(tx: CurationTransaction) -> None:
        tx.replace("draft", "d-1", 1, {"v": 2})
        tx.insert("revision", "d-1/2", {"conteudo": "x"})
        tx.append_event({"tipo": "editado"})
        raise RuntimeError("interrompido no meio do comando")

    with pytest.raises(RuntimeError, match="interrompido"):
        _in_transaction(store, interrupted)

    with store.transaction() as tx:
        draft = tx.get("draft", "d-1")
        revision = tx.get("revision", "d-1/2")
        events = tx.events()

    assert draft is not None
    assert (draft.version, draft.document) == (1, {"v": 1})
    assert revision is None
    assert events == ()


def test_events_keep_commit_order_with_increasing_sequence(
    tmp_path: Path, make_store: StoreFactory
) -> None:
    store = make_store(tmp_path)
    with store.transaction() as tx:
        first = tx.append_event({"n": 1})
        second = tx.append_event({"n": 2})
    with store.transaction() as tx:
        third = tx.append_event({"n": 3})
        listed = tx.events()
        after_first = tx.events(after_seq=first)

    assert first < second < third
    assert [document["n"] for _, document in listed] == [1, 2, 3]
    assert [seq for seq, _ in listed] == [first, second, third]
    assert [document["n"] for _, document in after_first] == [2, 3]


def test_scan_lists_records_of_one_kind_in_key_order(
    tmp_path: Path, make_store: StoreFactory
) -> None:
    store = make_store(tmp_path)
    with store.transaction() as tx:
        tx.insert("request", "r-b", {"k": "b"})
        tx.insert("request", "r-a", {"k": "a"})
        tx.insert("draft", "d-1", {"k": "d"})
    with store.transaction() as tx:
        requests = tx.scan("request")

    assert [record.key for record in requests] == ["r-a", "r-b"]
    assert {record.kind for record in requests} == {"request"}


def test_committed_records_and_events_survive_reopening(
    tmp_path: Path, make_store: StoreFactory
) -> None:
    store = make_store(tmp_path)
    with store.transaction() as tx:
        tx.insert("request", "r-1", {"estado": "open"})
        seq = tx.append_event({"tipo": "criado"})

    reopened = make_store(tmp_path)
    with reopened.transaction() as tx:
        record = tx.get("request", "r-1")
        events = tx.events()

    assert record is not None
    assert record.document == {"estado": "open"}
    assert events == ((seq, {"tipo": "criado"}),)


def test_injected_commit_failure_leaves_nothing_and_raises_unavailable(tmp_path: Path) -> None:
    store = SqliteTestCurationStore(tmp_path / "s.sqlite3", fail_at={"before_commit"})

    def writes(tx: CurationTransaction) -> None:
        tx.insert("request", "r-1", {"x": 1})
        tx.append_event({"tipo": "criado"})

    with pytest.raises(StoreUnavailableError, match="before_commit"):
        _in_transaction(store, writes)

    store.fail_at.clear()
    with store.transaction() as tx:
        assert tx.get("request", "r-1") is None
        assert tx.events() == ()


def test_transactions_that_read_then_write_never_interleave(
    tmp_path: Path, make_store: StoreFactory
) -> None:
    """Serializável: ler e depois gravar numa transação não sofre escrita enviesada.

    A reserva da linha de publicação depende disso: conferir que não há intenção em
    andamento e gravar a nova acontecem na mesma transação. Duas transações que tentam
    o mesmo ao mesmo tempo deixam exatamente um registro; a outra vê o primeiro (ou
    recebe conflito do armazenamento).
    """
    store = make_store(tmp_path)
    barrier = threading.Barrier(2)
    outcomes: dict[str, str] = {}

    def reserve(name: str) -> None:
        barrier.wait()
        try:
            with store.transaction() as tx:
                if any(record.document["state"] == "recorded" for record in tx.scan("intent")):
                    outcomes[name] = "recusada"
                    return
                time.sleep(0.05)
                tx.insert("intent", name, {"state": "recorded"})
                outcomes[name] = "reservou"
        except StoreError as exc:
            outcomes[name] = exc.code

    threads = [threading.Thread(target=reserve, args=(name,)) for name in ("a", "b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    with store.transaction() as tx:
        reserved = [record.key for record in tx.scan("intent")]

    assert not any(thread.is_alive() for thread in threads)
    assert len(reserved) == 1
    assert outcomes[reserved[0]] == "reservou"
    (other,) = (outcome for name, outcome in outcomes.items() if name != reserved[0])
    assert other in {"recusada", "store_conflict", "store_unavailable"}


def test_non_json_document_is_refused_without_partial_write(
    tmp_path: Path, make_store: StoreFactory
) -> None:
    store = make_store(tmp_path)

    def writes(tx: CurationTransaction) -> None:
        tx.insert("request", "r-0", {"x": 0})
        tx.insert("request", "r-1", {"x": object()})

    with pytest.raises(StoreError, match="JSON"):
        _in_transaction(store, writes)
    with store.transaction() as tx:
        assert tx.scan("request") == ()
