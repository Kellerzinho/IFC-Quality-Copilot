"""Repositórios da transação operacional, todos sobre a mesma conexão SQLite.

Cada tabela guarda o documento em JSON canônico com SHA-256 e repete, em colunas
próprias, a identidade extraída do documento (chaves, FKs, tokens). O banco impõe
chaves, unicidade, FKs e imutabilidade (gatilhos); a leitura confere hash, forma
canônica e colunas contra o documento, e qualquer divergência é erro de integridade.
Nenhum repositório confirma transação: o commit é da unidade de trabalho.
"""

import hashlib
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, NamedTuple

from src.domain_catalog.canonical import CanonicalJSONError, canonical_json_text, parse_json_strict
from src.domain_catalog.curation_errors import IdempotencyConflictError
from src.domain_catalog.draft_store import (
    StoreConflictError,
    StoreError,
    StoreUnavailableError,
)

EVENT_NAMESPACES: frozenset[str] = frozenset({"curation", "operations"})
COMMAND_STATES: frozenset[str] = frozenset({"in_progress", "completed", "abandoned"})


class StoreBusyError(StoreUnavailableError):
    """Outro escritor detém o banco além do ``busy_timeout``; nada foi gravado."""

    code = "store_busy"


class StoreIntegrityError(StoreError):
    """Registro persistido adulterado, fora da forma canônica ou incoerente com colunas."""

    code = "integrity_error"


class ReleaseHashCollisionError(StoreConflictError):
    """Mesmo catálogo e versão já retidos com outro hash de manifesto."""

    code = "version_hash_collision"


def sqlite_failure(exc: sqlite3.Error, action: str) -> StoreError:
    """Erro SQLite tipado pelo código do SQLite, nunca pelo texto da mensagem."""
    code = getattr(exc, "sqlite_errorcode", None)
    base = None if code is None else code & 0xFF
    if base in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
        return StoreBusyError(f"store_busy: banco ocupado por outro escritor ({action})")
    if isinstance(exc, sqlite3.IntegrityError):
        return StoreConflictError(f"conflito no armazenamento ({action}): {exc}")
    return StoreUnavailableError(f"falha do armazenamento ({action}): {exc}")


def encode_document(document: Mapping[str, Any]) -> tuple[str, str]:
    """Texto JSON canônico e seu SHA-256; tipos preservados, NaN e objetos recusados."""
    try:
        text = canonical_json_text(dict(document))
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise StoreError(f"documento não é JSON canônico representável: {exc}") from exc
    return text, digest


def decode_document(payload: str, digest: str, where: str) -> dict[str, Any]:
    """Documento verificado; hash, forma canônica e tipo objeto são exigidos."""
    if hashlib.sha256(payload.encode("utf-8")).hexdigest() != digest:
        raise StoreIntegrityError(f"integrity: hash divergente em {where}")
    try:
        document = parse_json_strict(payload)
    except CanonicalJSONError as exc:
        raise StoreIntegrityError(f"integrity: JSON inválido em {where}: {exc}") from exc
    if not isinstance(document, dict) or canonical_json_text(document) != payload:
        raise StoreIntegrityError(f"integrity: documento fora da forma canônica em {where}")
    return document


Extractor = Callable[[Mapping[str, Any]], object]


def field(*path: str) -> Extractor:
    """Extrai um valor do documento pelo caminho; ausência é erro do documento."""

    def extract(document: Mapping[str, Any]) -> object:
        value: Any = document
        for part in path:
            if not isinstance(value, Mapping) or part not in value:
                raise StoreError(f"documento sem o campo {'.'.join(path)}")
            value = value[part]
        return value

    return extract


def constant(value: object) -> Extractor:
    """Coluna de valor fixo (por exemplo, o papel exigido numa FK)."""
    return lambda document: value


def _column_value(value: object) -> object:
    """Booleano vira 0/1 no SQLite; texto, inteiro e nulo seguem como estão."""
    if isinstance(value, bool):
        return int(value)
    if value is None or isinstance(value, (str, int)):
        return value
    raise StoreError(f"coluna de identidade não aceita {type(value).__name__}")


@dataclass(frozen=True)
class TableSpec:
    """Tabela tipada: chave, colunas de identidade e extratores a partir do documento."""

    table: str
    key: tuple[str, ...]
    columns: tuple[str, ...]
    extract: Mapping[str, Extractor]
    mutable: bool


class StoredRow(NamedTuple):
    """Cópia verificada de uma linha: chave, versão da linha (CAS) e documento."""

    key: tuple[object, ...]
    row_version: int
    document: dict[str, Any]


class Table:
    """Acesso parametrizado a uma tabela tipada; nomes vêm só das especificações."""

    def __init__(self, connection: sqlite3.Connection, spec: TableSpec) -> None:
        """Liga a especificação à conexão da unidade de trabalho."""
        self._connection = connection
        self.spec = spec
        self._all = (*spec.key, *spec.columns)

    def _execute(self, sql: str, parameters: tuple[object, ...], action: str) -> sqlite3.Cursor:
        try:
            return self._connection.execute(sql, parameters)
        except sqlite3.Error as exc:
            raise sqlite_failure(exc, f"{action} {self.spec.table}") from exc

    def _values(self, document: Mapping[str, Any]) -> tuple[object, ...]:
        return tuple(_column_value(self.spec.extract[name](document)) for name in self._all)

    def _row(self, row: tuple[Any, ...]) -> StoredRow:
        size = len(self._all)
        values, row_version, payload, digest = row[:size], row[size], row[size + 1], row[size + 2]
        where = f"{self.spec.table} {values[: len(self.spec.key)]}"
        document = decode_document(payload, digest, where)
        if self._values(document) != tuple(values):
            raise StoreIntegrityError(f"integrity: colunas de identidade divergem em {where}")
        return StoredRow(tuple(values[: len(self.spec.key)]), row_version, document)

    def _select(self) -> str:
        names = ", ".join(self._all)
        return f"SELECT {names}, row_version, payload, payload_sha256 FROM {self.spec.table}"

    def get(self, *key: object) -> StoredRow | None:
        """Linha pela chave completa, verificada; ausência é ``None``."""
        if len(key) != len(self.spec.key):
            raise ValueError(f"{self.spec.table} tem chave {self.spec.key}")
        where = " AND ".join(f"{name} = ?" for name in self.spec.key)
        row = self._execute(
            f"{self._select()} WHERE {where}", tuple(_column_value(k) for k in key), "ler"
        ).fetchone()
        return None if row is None else self._row(row)

    def scan(self, **equals: object) -> tuple[StoredRow, ...]:
        """Linhas que igualam as colunas dadas, em ordem de chave."""
        unknown = set(equals) - set(self._all)
        if unknown:
            raise ValueError(f"colunas desconhecidas em {self.spec.table}: {sorted(unknown)}")
        names = sorted(equals)
        clause = (" WHERE " + " AND ".join(f"{name} = ?" for name in names)) if names else ""
        order = ", ".join(self.spec.key)
        rows = self._execute(
            f"{self._select()}{clause} ORDER BY {order}",
            tuple(_column_value(equals[name]) for name in names),
            "listar",
        ).fetchall()
        return tuple(self._row(row) for row in rows)

    def latest(self, **equals: object) -> StoredRow | None:
        """Linha mais recentemente inserida que iguala as colunas dadas (ordem de inserção)."""
        unknown = set(equals) - set(self._all)
        if unknown:
            raise ValueError(f"colunas desconhecidas em {self.spec.table}: {sorted(unknown)}")
        names = sorted(equals)
        clause = (" WHERE " + " AND ".join(f"{name} = ?" for name in names)) if names else ""
        row = self._execute(
            f"{self._select()}{clause} ORDER BY rowid DESC LIMIT 1",
            tuple(_column_value(equals[name]) for name in names),
            "ler",
        ).fetchone()
        return None if row is None else self._row(row)

    def scan_inserted(self, **equals: object) -> tuple[StoredRow, ...]:
        """Linhas que igualam as colunas dadas, na ordem de inserção."""
        unknown = set(equals) - set(self._all)
        if unknown:
            raise ValueError(f"colunas desconhecidas em {self.spec.table}: {sorted(unknown)}")
        names = sorted(equals)
        clause = (" WHERE " + " AND ".join(f"{name} = ?" for name in names)) if names else ""
        rows = self._execute(
            f"{self._select()}{clause} ORDER BY rowid",
            tuple(_column_value(equals[name]) for name in names),
            "listar",
        ).fetchall()
        return tuple(self._row(row) for row in rows)

    def insert(self, document: Mapping[str, Any]) -> StoredRow:
        """Cria a linha na versão 1; chave existente ou FK inválida é conflito."""
        payload, digest = encode_document(document)
        values = self._values(document)
        names = ", ".join((*self._all, "row_version", "payload", "payload_sha256"))
        marks = ", ".join("?" for _ in range(len(values) + 3))
        self._execute(
            f"INSERT INTO {self.spec.table} ({names}) VALUES ({marks})",
            (*values, 1, payload, digest),
            "inserir",
        )
        return StoredRow(values[: len(self.spec.key)], 1, parse_json_strict(payload))

    def replace(
        self, key: object, expected_row_version: int, document: Mapping[str, Any]
    ) -> StoredRow:
        """Troca o documento se a versão da linha for a esperada (CAS) e a chave a mesma.

        ``key`` é a tupla da chave; chave de uma coluna pode vir sem tupla.
        """
        key = key if isinstance(key, tuple) else (key,)
        if not self.spec.mutable:
            raise StoreConflictError(f"{self.spec.table} é imutável: use insert")
        payload, digest = encode_document(document)
        values = self._values(document)
        key_values = tuple(_column_value(k) for k in key)
        if values[: len(self.spec.key)] != key_values:
            raise StoreConflictError(f"{self.spec.table}: documento não pertence à chave {key}")
        assignments = ", ".join(f"{name} = ?" for name in self.spec.columns)
        prefix = f"{assignments}, " if assignments else ""
        where = " AND ".join(f"{name} = ?" for name in self.spec.key)
        cursor = self._execute(
            f"UPDATE {self.spec.table} SET {prefix}row_version = row_version + 1, "
            f"payload = ?, payload_sha256 = ? WHERE {where} AND row_version = ?",
            (*values[len(self.spec.key) :], payload, digest, *key_values, expected_row_version),
            "trocar",
        )
        if cursor.rowcount != 1:
            current = self.get(*key)
            found = "ausente" if current is None else f"versão {current.row_version}"
            raise StoreConflictError(
                f"{self.spec.table} {key}: esperada versão {expected_row_version}, {found}"
            )
        return StoredRow(key_values, expected_row_version + 1, parse_json_strict(payload))


class VersionedRepository:
    """Revisões imutáveis e um head mutável (CAS) da mesma família de registros."""

    def __init__(self, connection: sqlite3.Connection, revisions: TableSpec, heads: TableSpec):
        """Liga as duas tabelas à mesma conexão."""
        self.revisions = Table(connection, revisions)
        self.heads = Table(connection, heads)

    def insert_revision(self, document: Mapping[str, Any]) -> StoredRow:
        """Revisão nova, imutável."""
        return self.revisions.insert(document)

    def get_revision(self, *key: object) -> StoredRow | None:
        """Revisão exata pela chave."""
        return self.revisions.get(*key)

    def scan_revisions(self, **equals: object) -> tuple[StoredRow, ...]:
        """Revisões filtradas por colunas de identidade."""
        return self.revisions.scan(**equals)

    def get_head(self, *key: object) -> StoredRow | None:
        """Head atual pela chave."""
        return self.heads.get(*key)

    def scan_heads(self, **equals: object) -> tuple[StoredRow, ...]:
        """Heads filtrados por colunas de identidade."""
        return self.heads.scan(**equals)

    def insert_head(self, document: Mapping[str, Any]) -> StoredRow:
        """Primeiro head da família."""
        return self.heads.insert(document)

    def replace_head(
        self, key: object, expected_row_version: int, document: Mapping[str, Any]
    ) -> StoredRow:
        """Avança o head por CAS."""
        return self.heads.replace(key, expected_row_version, document)


class ReleaseRepository(Table):
    """Releases retidos: ``(catalog_id, version)`` aponta um único hash de manifesto."""

    def insert_or_verify(self, document: Mapping[str, Any]) -> StoredRow:
        """Registra o release ou confere o já retido; hash diferente é colisão."""
        catalog = field("catalog")(document)
        assert isinstance(catalog, Mapping)
        existing = self.get(catalog["catalog_id"], catalog["version"])
        if existing is None:
            return self.insert(document)
        stored = existing.document["catalog"]["manifest_sha256"]
        if stored != catalog["manifest_sha256"]:
            raise ReleaseHashCollisionError(
                f"version_hash_collision: {catalog['catalog_id']} {catalog['version']} já "
                f"retido com manifesto {stored}"
            )
        return existing


class CommandRow(NamedTuple):
    """Reserva do índice global de comandos e o recibo operacional, quando houver."""

    command_id: str
    namespace: str
    operation: str
    payload_sha256: str
    actor_context_id: str
    record_ref: str
    state: str
    receipt: dict[str, Any] | None


_IDENTITY = ("namespace", "operation", "payload_sha256", "actor_context_id", "record_ref")


class CommandRepository:
    """Índice único de comandos de curadoria e de operações na instalação."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        """Usa a conexão da unidade de trabalho."""
        self._connection = connection

    def _execute(self, sql: str, parameters: tuple[object, ...], action: str) -> sqlite3.Cursor:
        try:
            return self._connection.execute(sql, parameters)
        except sqlite3.Error as exc:
            raise sqlite_failure(exc, f"{action} comando") from exc

    def get(self, command_id: str) -> CommandRow | None:
        """Reserva pela chave, com recibo verificado; ausência é ``None``."""
        row = self._execute(
            "SELECT command_id, namespace, operation, payload_sha256, actor_context_id, "
            "record_ref, state, receipt, receipt_sha256 FROM commands WHERE command_id = ?",
            (command_id,),
            "ler",
        ).fetchone()
        if row is None:
            return None
        receipt = None if row[7] is None else decode_document(row[7], row[8], f"comando {row[0]}")
        return CommandRow(
            command_id=row[0],
            namespace=row[1],
            operation=row[2],
            payload_sha256=row[3],
            actor_context_id=row[4],
            record_ref=row[5],
            state=row[6],
            receipt=receipt,
        )

    def reserve(
        self,
        *,
        command_id: str,
        namespace: str,
        operation: str,
        payload_sha256: str,
        actor_context_id: str,
        record_ref: str,
    ) -> CommandRow:
        """Reserva a chave ou devolve a reserva idêntica; qualquer diferença é conflito."""
        if namespace not in EVENT_NAMESPACES:
            raise ValueError(f"namespace de comando inválido: {namespace}")
        wanted = (namespace, operation, payload_sha256, actor_context_id, record_ref)
        existing = self.get(command_id)
        if existing is not None:
            found = tuple(getattr(existing, name) for name in _IDENTITY)
            if found != wanted:
                raise IdempotencyConflictError(
                    f"idempotency_conflict: chave {command_id} já reservada por "
                    f"{existing.namespace}/{existing.operation}"
                )
            return existing
        self._execute(
            "INSERT INTO commands (command_id, namespace, operation, payload_sha256, "
            "actor_context_id, record_ref, state) VALUES (?, ?, ?, ?, ?, ?, 'in_progress')",
            (command_id, *wanted),
            "reservar",
        )
        return CommandRow(command_id, *wanted, state="in_progress", receipt=None)

    def _transition(
        self, command_id: str, state: str, receipt: Mapping[str, Any] | None
    ) -> CommandRow:
        current = self.get(command_id)
        if current is None:
            raise StoreConflictError(f"comando {command_id} não reservado")
        if current.state != "in_progress":
            raise StoreConflictError(f"comando {command_id} já está em {current.state}")
        payload, digest = (None, None) if receipt is None else encode_document(receipt)
        self._execute(
            "UPDATE commands SET state = ?, receipt = ?, receipt_sha256 = ? "
            "WHERE command_id = ? AND state = 'in_progress'",
            (state, payload, digest, command_id),
            "concluir",
        )
        return current._replace(
            state=state, receipt=None if payload is None else parse_json_strict(payload)
        )

    def complete(self, command_id: str, receipt: Mapping[str, Any] | None) -> CommandRow:
        """Conclui a reserva em andamento, guardando o recibo operacional quando houver."""
        return self._transition(command_id, "completed", receipt)

    def abandon(self, command_id: str) -> CommandRow:
        """Marca a reserva em andamento como abandonada, sem apagar a identidade."""
        return self._transition(command_id, "abandoned", None)


class EventRepository:
    """Log global de eventos com namespace; sequência única e crescente."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        """Usa a conexão da unidade de trabalho."""
        self._connection = connection

    def append(self, namespace: str, document: Mapping[str, Any]) -> int:
        """Grava o evento na transação corrente e devolve a sequência global."""
        if namespace not in EVENT_NAMESPACES:
            raise ValueError(f"namespace de evento inválido: {namespace}")
        payload, digest = encode_document(document)
        try:
            cursor = self._connection.execute(
                "INSERT INTO events (namespace, payload, payload_sha256) VALUES (?, ?, ?)",
                (namespace, payload, digest),
            )
        except sqlite3.Error as exc:
            raise sqlite_failure(exc, "gravar evento") from exc
        if cursor.lastrowid is None:
            raise StoreUnavailableError("o banco não devolveu a sequência do evento")
        return cursor.lastrowid

    def list(
        self, after_seq: int = 0, namespace: str | None = None
    ) -> tuple[tuple[int, dict[str, Any]], ...]:
        """Eventos confirmados depois da sequência, opcionalmente de um namespace."""
        if namespace is not None and namespace not in EVENT_NAMESPACES:
            raise ValueError(f"namespace de evento inválido: {namespace}")
        try:
            rows = self._connection.execute(
                "SELECT seq, payload, payload_sha256 FROM events WHERE seq > ? "
                "AND (? IS NULL OR namespace = ?) ORDER BY seq",
                (after_seq, namespace, namespace),
            ).fetchall()
        except sqlite3.Error as exc:
            raise sqlite_failure(exc, "listar eventos") from exc
        return tuple((row[0], decode_document(row[1], row[2], f"evento {row[0]}")) for row in rows)


CURATION_KINDS: tuple[str, ...] = (
    "request",
    "draft",
    "revision",
    "review",
    "candidate",
    "intent",
    "publication",
    "command",
)


class CurationRecordRow(NamedTuple):
    """Registro de curadoria E2 verificado, com a versão da porta (CAS)."""

    kind: str
    key: str
    version: int
    document: dict[str, Any]


class CurationRecordRepository:
    """Documentos da porta ``CurationStore`` E2, com tipo e chave preservados."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        """Usa a conexão da unidade de trabalho."""
        self._connection = connection

    def _execute(self, sql: str, parameters: tuple[object, ...], action: str) -> sqlite3.Cursor:
        try:
            return self._connection.execute(sql, parameters)
        except sqlite3.Error as exc:
            raise sqlite_failure(exc, f"{action} registro de curadoria") from exc

    def _row(self, row: tuple[Any, ...]) -> CurationRecordRow:
        document = decode_document(row[3], row[4], f"curadoria {row[0]} {row[1]}")
        return CurationRecordRow(row[0], row[1], row[2], document)

    def get(self, kind: str, key: str) -> CurationRecordRow | None:
        """Registro pela chave, ou ``None``."""
        row = self._execute(
            "SELECT kind, record_key, version, payload, payload_sha256 FROM curation_records "
            "WHERE kind = ? AND record_key = ?",
            (kind, key),
            "ler",
        ).fetchone()
        return None if row is None else self._row(row)

    def scan(self, kind: str) -> tuple[CurationRecordRow, ...]:
        """Registros de um tipo em ordem de chave."""
        rows = self._execute(
            "SELECT kind, record_key, version, payload, payload_sha256 FROM curation_records "
            "WHERE kind = ? ORDER BY record_key",
            (kind,),
            "listar",
        ).fetchall()
        return tuple(self._row(row) for row in rows)

    def insert(self, kind: str, key: str, document: Mapping[str, Any]) -> CurationRecordRow:
        """Cria na versão 1; chave existente é conflito."""
        payload, digest = encode_document(document)
        self._execute(
            "INSERT INTO curation_records (kind, record_key, version, payload, payload_sha256) "
            "VALUES (?, ?, 1, ?, ?)",
            (kind, key, payload, digest),
            "inserir",
        )
        return CurationRecordRow(kind, key, 1, parse_json_strict(payload))

    def replace(
        self, kind: str, key: str, expected_version: int, document: Mapping[str, Any]
    ) -> CurationRecordRow:
        """Troca com versão esperada; ausente ou outra versão é conflito."""
        payload, digest = encode_document(document)
        cursor = self._execute(
            "UPDATE curation_records SET version = version + 1, payload = ?, payload_sha256 = ? "
            "WHERE kind = ? AND record_key = ? AND version = ?",
            (payload, digest, kind, key, expected_version),
            "trocar",
        )
        if cursor.rowcount != 1:
            current = self.get(kind, key)
            found = "ausente" if current is None else f"versão {current.version}"
            raise StoreConflictError(f"{kind} {key}: esperada versão {expected_version}, {found}")
        return CurationRecordRow(kind, key, expected_version + 1, parse_json_strict(payload))
