"""``CurationStore`` E2 sobre a autoridade operacional real (``operations.sqlite3``).

Implementa exatamente a porta ``CurationStore``/``CurationTransaction``: tipos de
registro, documentos JSON, versão com CAS, eventos e reabertura, sem ampliar enums
nem recibos da E2. Registros ficam em ``curation_records``; eventos no log global com
namespace ``curation``. Todo registro ``command`` reserva ou atualiza, **na mesma
transação**, o índice global de comandos compartilhado com as operações E3: a mesma
chave em namespace diferente é ``IdempotencyConflictError`` nas duas direções, e o
``CommandRecord`` E2 continua sendo o payload autoritativo do comando de curadoria.
``operational=True`` significa backend durável implementado, não autenticação nem
prontidão de produção.
"""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from src.domain_catalog.curation_errors import IdempotencyConflictError
from src.domain_catalog.draft_store import RecordKind, StoredRecord, StoreError
from src.operations.database import OperationalStore, OperationalUnitOfWork
from src.operations.repositories import CommandRow, CurationRecordRow


def curation_record_ref(key: str) -> str:
    """Referência do registro E2 que detém a reserva no índice global."""
    return f"curation_records/command/{key}"


def _identity(document: Mapping[str, Any]) -> tuple[str, str, str, str]:
    try:
        return (
            str(document["operation"]),
            str(document["payload_sha256"]),
            str(document["actor_context_id"]),
            str(document["state"]),
        )
    except KeyError as exc:
        raise StoreError(f"registro de comando E2 sem o campo {exc.args[0]}") from exc


def _record(row: CurationRecordRow) -> StoredRecord:
    return StoredRecord(kind=row.kind, key=row.key, version=row.version, document=row.document)  # type: ignore[arg-type]


class _CurationTransaction:
    """Transação da porta E2 sobre a unidade de trabalho operacional."""

    def __init__(self, uow: OperationalUnitOfWork) -> None:
        self._uow = uow

    def _guard_index(self, key: str) -> CommandRow | None:
        row = self._uow.commands.get(key)
        if row is not None and row.namespace != "curation":
            raise IdempotencyConflictError(
                f"chave {key} já reservada por {row.namespace}/{row.operation}; use uma chave nova"
            )
        return row

    def _sync_state(self, key: str, state: str) -> None:
        row = self._uow.commands.get(key)
        assert row is not None
        if state == row.state:
            return
        if state == "completed":
            self._uow.commands.complete(key, None)
        elif state == "abandoned":
            self._uow.commands.abandon(key)
        else:
            raise StoreError(f"transição de comando E2 não suportada: {row.state} → {state}")

    def get(self, kind: RecordKind, key: str) -> StoredRecord | None:
        """Registro pela chave; chave de comando de outro namespace é conflito."""
        if kind == "command":
            self._guard_index(key)
        row = self._uow.curation.get(kind, key)
        return None if row is None else _record(row)

    def scan(self, kind: RecordKind) -> tuple[StoredRecord, ...]:
        """Registros de um tipo, em ordem de chave."""
        return tuple(_record(row) for row in self._uow.curation.scan(kind))

    def insert(self, kind: RecordKind, key: str, document: Mapping[str, Any]) -> StoredRecord:
        """Cria na versão 1; comando reserva o índice global na mesma transação."""
        if kind == "command":
            operation, payload, actor, state = _identity(document)
            self._guard_index(key)
            self._uow.commands.reserve(
                command_id=key,
                namespace="curation",
                operation=operation,
                payload_sha256=payload,
                actor_context_id=actor,
                record_ref=curation_record_ref(key),
            )
            self._sync_state(key, state)
        return _record(self._uow.curation.insert(kind, key, document))

    def replace(
        self, kind: RecordKind, key: str, expected_version: int, document: Mapping[str, Any]
    ) -> StoredRecord:
        """Troca com versão esperada; estado do comando muda sem mudar sua identidade."""
        if kind == "command":
            operation, payload, actor, state = _identity(document)
            row = self._guard_index(key)
            if row is None:
                raise StoreError(f"comando E2 {key} sem reserva no índice global")
            if (row.operation, row.payload_sha256, row.actor_context_id) != (
                operation,
                payload,
                actor,
            ):
                raise IdempotencyConflictError(
                    f"comando {key}: atualização não pode mudar operação, payload ou ator"
                )
            self._sync_state(key, state)
        return _record(self._uow.curation.replace(kind, key, expected_version, document))

    def append_event(self, document: Mapping[str, Any]) -> int:
        """Evento de curadoria no log global; devolve a sequência global."""
        return self._uow.events.append("curation", document)

    def events(self, after_seq: int = 0) -> tuple[tuple[int, dict[str, Any]], ...]:
        """Eventos de curadoria confirmados depois da sequência dada."""
        return self._uow.events.list(after_seq, namespace="curation")


class SQLiteCurationStore:
    """Adaptador durável da porta de curadoria sobre a autoridade operacional."""

    def __init__(self, store: OperationalStore) -> None:
        """Usa o mesmo banco das operações; não abre segundo banco."""
        self._store = store

    @property
    def operational(self) -> bool:
        """Backend durável implementado (não significa autenticação nem produção)."""
        return True

    @property
    def operational_store(self) -> OperationalStore:
        """Autoridade operacional subjacente."""
        return self._store

    @contextmanager
    def transaction(self) -> Iterator[_CurationTransaction]:
        """Commit na saída normal; exceção desfaz registros, eventos e reservas."""
        with self._store.transaction() as uow:
            yield _CurationTransaction(uow)
