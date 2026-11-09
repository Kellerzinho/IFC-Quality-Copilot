"""Banco operacional local (``operations.sqlite3``): migração, transação e unidade de trabalho.

``OperationalStore.open(root)`` cria ou abre **um** banco por raiz. A criação exige
``purpose`` (``operational`` ou ``synthetic_test``), gravado uma vez e imutável. Cada
transação usa conexão própria com ``foreign_keys=ON``, ``journal_mode=WAL``,
``synchronous=FULL`` e ``busy_timeout`` finito, e abre com ``BEGIN IMMEDIATE`` (um
escritor por vez); lock além do prazo vira ``StoreBusyError``, sem retry infinito.
Migrações são numeradas e transacionais; banco de versão futura é recusado. Abrir o
banco não adquire lock de execução de análise nem recupera runs: isso pertence ao
coordenador de análise. ``operational=True`` nos adaptadores significa backend
durável implementado, não autenticação nem prontidão de produção.
"""

import sqlite3
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Final, Literal, get_args

from src.domain_catalog.canonical import canonical_json_bytes
from src.domain_catalog.curation import utc_now
from src.domain_catalog.draft_store import StoreError, StoreUnavailableError
from src.operations.repositories import (
    CURATION_KINDS,
    CommandRepository,
    CurationRecordRepository,
    EventRepository,
    Extractor,
    ReleaseHashCollisionError,
    ReleaseRepository,
    StoreBusyError,
    StoreIntegrityError,
    Table,
    TableSpec,
    VersionedRepository,
    constant,
    field,
    sqlite_failure,
)

__all__ = [
    "DB_FILE",
    "SCHEMA_VERSION",
    "OperationalStore",
    "OperationalUnitOfWork",
    "ReleaseHashCollisionError",
    "StoreBusyError",
    "StoreIntegrityError",
    "StorePurpose",
    "StorePurposeError",
    "StoreSchemaError",
]

StorePurpose = Literal["operational", "synthetic_test"]
DB_FILE: Final = "operations.sqlite3"
DEFAULT_BUSY_TIMEOUT_MS: Final = 5000


class StoreSchemaError(StoreError):
    """Banco com versão de schema futura ou desconhecida; não é aberto nem migrado."""

    code = "schema_unsupported"


class StorePurposeError(StoreError):
    """Propósito ausente na criação ou diferente do gravado; nunca é trocado."""

    code = "purpose_mismatch"


def _sha(document: object) -> str:
    import hashlib

    return hashlib.sha256(canonical_json_bytes(document)).hexdigest()


def _hash_of(*path: str) -> Extractor:
    """Extrator de coluna com o SHA-256 canônico de um subdocumento (ou do documento)."""
    getter = field(*path) if path else None

    def extract(document: Mapping[str, Any]) -> object:
        return _sha(document if getter is None else getter(document))

    return extract


def _spec(
    table: str,
    key: tuple[str, ...],
    columns: dict[str, Extractor | None],
    *,
    mutable: bool,
) -> TableSpec:
    extract: dict[str, Extractor] = {name: field(name) for name in key}
    for name, source in columns.items():
        extract[name] = source if source is not None else field(name)
    return TableSpec(table, key, tuple(columns), extract, mutable)


_SELF: Extractor | None = None
"""Marcador: a coluna tem o mesmo nome do campo de topo do documento."""

ACTOR_CONTEXTS = _spec(
    "actor_contexts",
    ("actor_context_id",),
    {"actor_kind": _SELF, "installation_id": _SELF, "session_id": _SELF},
    mutable=False,
)
PROJECTS = _spec("projects", ("project_id",), {"pair_set_revision": _SELF}, mutable=True)
MODELS = _spec("models", ("model_id",), {"project_id": _SELF}, mutable=False)
SOURCE_REVISIONS = _spec(
    "source_revisions",
    ("source_id", "revision"),
    {
        "project_id": _SELF,
        "model_id": _SELF,
        "role": _SELF,
        "sha256": _SELF,
        "size_bytes": _SELF,
        "storage_key": _SELF,
    },
    mutable=False,
)
SOURCE_HEADS = _spec(
    "source_heads",
    ("source_id",),
    {"revision": _SELF, "project_id": _SELF, "model_id": _SELF, "role": _SELF},
    mutable=True,
)
PAIR_REVISIONS = _spec(
    "pair_revisions",
    ("pair_id", "pair_revision"),
    {
        "project_id": _SELF,
        "model_id": _SELF,
        "ifc_source_id": field("ifc", "source_id"),
        "ifc_revision": field("ifc", "revision"),
        "ifc_role": constant("ifc"),
        "ids_source_id": field("ids", "source_id"),
        "ids_revision": field("ids", "revision"),
        "ids_role": constant("ids"),
        "active": _SELF,
    },
    mutable=False,
)
PAIR_HEADS = _spec(
    "project_pair_heads",
    ("pair_id",),
    {"pair_revision": _SELF, "project_id": _SELF, "active": _SELF},
    mutable=True,
)
CATALOG_RELEASES = TableSpec(
    "catalog_releases",
    ("catalog_id", "version"),
    ("manifest_sha256", "storage_key"),
    {
        "catalog_id": field("catalog", "catalog_id"),
        "version": field("catalog", "version"),
        "manifest_sha256": field("catalog", "manifest_sha256"),
        "storage_key": field("storage_key"),
    },
    False,
)
PIN_REVISIONS = _spec(
    "project_pin_revisions",
    ("project_id", "pin_revision"),
    {
        "catalog_id": field("catalog", "catalog_id"),
        "version": field("catalog", "version"),
        "manifest_sha256": field("catalog", "manifest_sha256"),
        "adoption_id": _SELF,
        "previous_pin_revision": _SELF,
    },
    mutable=False,
)
PIN_HEADS = _spec("project_pin_heads", ("project_id",), {"pin_revision": _SELF}, mutable=True)
ADOPTION_PLANS = _spec(
    "adoption_plans",
    ("plan_id",),
    {"project_id": _SELF, "plan_sha256": _hash_of()},
    mutable=False,
)
ANALYSIS_RUNS = _spec(
    "analysis_runs",
    ("analysis_id",),
    {
        "project_id": field("identity", "project_id"),
        "pair_id": field("identity", "pair_id"),
        "pair_revision": field("identity", "pair_revision"),
        "pin_revision": field("identity", "pin_revision"),
        "state": _SELF,
        "identity_sha256": _hash_of("identity"),
        "parent_analysis_id": _SELF,
    },
    mutable=True,
)
DIAGNOSTIC_SNAPSHOTS = _spec(
    "diagnostic_snapshots",
    ("snapshot_id",),
    {"analysis_id": field("identity", "analysis_id"), "content_sha256": _SELF},
    mutable=False,
)
ENRICHMENT_RUNS = _spec(
    "enrichment_runs",
    ("enrichment_id",),
    {"analysis_id": _SELF, "snapshot_id": _SELF},
    mutable=False,
)
CONTEXT_CACHE = _spec("context_cache", ("cache_key",), {"analysis_id": _SELF}, mutable=False)

_DOC = (
    "row_version INTEGER NOT NULL CHECK (row_version >= 1), payload TEXT NOT NULL, "
    "payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64)"
)
_UUID = "CHECK (length({0}) = 36)"
_SHA = "CHECK (length({0}) = 64)"

_TABLES_V1: tuple[str, ...] = (
    "CREATE TABLE store_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    f"""CREATE TABLE actor_contexts (
        actor_context_id TEXT PRIMARY KEY {_UUID.format("actor_context_id")},
        actor_kind TEXT NOT NULL CHECK (actor_kind IN ('human', 'assistant', 'service')),
        installation_id TEXT NOT NULL, session_id TEXT NOT NULL, {_DOC})""",
    f"""CREATE TABLE projects (
        project_id TEXT PRIMARY KEY {_UUID.format("project_id")},
        pair_set_revision INTEGER NOT NULL CHECK (pair_set_revision >= 0), {_DOC})""",
    f"""CREATE TABLE models (
        model_id TEXT PRIMARY KEY {_UUID.format("model_id")},
        project_id TEXT NOT NULL REFERENCES projects (project_id), {_DOC},
        UNIQUE (model_id, project_id))""",
    f"""CREATE TABLE source_revisions (
        source_id TEXT NOT NULL {_UUID.format("source_id")},
        revision INTEGER NOT NULL CHECK (revision >= 1),
        project_id TEXT NOT NULL REFERENCES projects (project_id),
        model_id TEXT NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('ifc', 'ids')),
        sha256 TEXT NOT NULL {_SHA.format("sha256")},
        size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
        storage_key TEXT NOT NULL, {_DOC},
        PRIMARY KEY (source_id, revision),
        FOREIGN KEY (model_id, project_id) REFERENCES models (model_id, project_id),
        UNIQUE (source_id, revision, project_id, model_id, role))""",
    f"""CREATE TABLE source_heads (
        source_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, project_id TEXT NOT NULL,
        model_id TEXT NOT NULL, role TEXT NOT NULL, {_DOC},
        FOREIGN KEY (source_id, revision, project_id, model_id, role)
            REFERENCES source_revisions (source_id, revision, project_id, model_id, role))""",
    f"""CREATE TABLE pair_revisions (
        pair_id TEXT NOT NULL {_UUID.format("pair_id")},
        pair_revision INTEGER NOT NULL CHECK (pair_revision >= 1),
        project_id TEXT NOT NULL REFERENCES projects (project_id),
        model_id TEXT NOT NULL,
        ifc_source_id TEXT NOT NULL, ifc_revision INTEGER NOT NULL,
        ifc_role TEXT NOT NULL CHECK (ifc_role = 'ifc'),
        ids_source_id TEXT NOT NULL, ids_revision INTEGER NOT NULL,
        ids_role TEXT NOT NULL CHECK (ids_role = 'ids'),
        active INTEGER NOT NULL CHECK (active IN (0, 1)), {_DOC},
        PRIMARY KEY (pair_id, pair_revision),
        FOREIGN KEY (model_id, project_id) REFERENCES models (model_id, project_id),
        FOREIGN KEY (ifc_source_id, ifc_revision, project_id, model_id, ifc_role)
            REFERENCES source_revisions (source_id, revision, project_id, model_id, role),
        FOREIGN KEY (ids_source_id, ids_revision, project_id, model_id, ids_role)
            REFERENCES source_revisions (source_id, revision, project_id, model_id, role),
        UNIQUE (pair_id, pair_revision, project_id, active))""",
    f"""CREATE TABLE project_pair_heads (
        pair_id TEXT PRIMARY KEY, pair_revision INTEGER NOT NULL,
        project_id TEXT NOT NULL REFERENCES projects (project_id),
        active INTEGER NOT NULL CHECK (active IN (0, 1)), {_DOC},
        FOREIGN KEY (pair_id, pair_revision, project_id, active)
            REFERENCES pair_revisions (pair_id, pair_revision, project_id, active))""",
    f"""CREATE TABLE catalog_releases (
        catalog_id TEXT NOT NULL, version TEXT NOT NULL,
        manifest_sha256 TEXT NOT NULL {_SHA.format("manifest_sha256")},
        storage_key TEXT NOT NULL, {_DOC},
        PRIMARY KEY (catalog_id, version),
        UNIQUE (catalog_id, version, manifest_sha256))""",
    f"""CREATE TABLE project_pin_revisions (
        project_id TEXT NOT NULL REFERENCES projects (project_id),
        pin_revision INTEGER NOT NULL CHECK (pin_revision >= 1),
        catalog_id TEXT NOT NULL, version TEXT NOT NULL, manifest_sha256 TEXT NOT NULL,
        adoption_id TEXT NOT NULL UNIQUE {_UUID.format("adoption_id")},
        previous_pin_revision INTEGER, {_DOC},
        PRIMARY KEY (project_id, pin_revision),
        FOREIGN KEY (catalog_id, version, manifest_sha256)
            REFERENCES catalog_releases (catalog_id, version, manifest_sha256),
        FOREIGN KEY (project_id, previous_pin_revision)
            REFERENCES project_pin_revisions (project_id, pin_revision),
        CHECK (previous_pin_revision IS NULL OR previous_pin_revision = pin_revision - 1))""",
    f"""CREATE TABLE project_pin_heads (
        project_id TEXT PRIMARY KEY REFERENCES projects (project_id),
        pin_revision INTEGER NOT NULL, {_DOC},
        FOREIGN KEY (project_id, pin_revision)
            REFERENCES project_pin_revisions (project_id, pin_revision))""",
    f"""CREATE TABLE adoption_plans (
        plan_id TEXT PRIMARY KEY {_UUID.format("plan_id")},
        project_id TEXT NOT NULL REFERENCES projects (project_id),
        plan_sha256 TEXT NOT NULL UNIQUE {_SHA.format("plan_sha256")}, {_DOC})""",
    f"""CREATE TABLE analysis_runs (
        analysis_id TEXT PRIMARY KEY {_UUID.format("analysis_id")},
        project_id TEXT NOT NULL REFERENCES projects (project_id),
        pair_id TEXT NOT NULL, pair_revision INTEGER NOT NULL, pin_revision INTEGER,
        state TEXT NOT NULL
            CHECK (state IN ('queued', 'running', 'completed', 'failed', 'interrupted')),
        identity_sha256 TEXT NOT NULL {_SHA.format("identity_sha256")},
        parent_analysis_id TEXT REFERENCES analysis_runs (analysis_id), {_DOC},
        FOREIGN KEY (pair_id, pair_revision) REFERENCES pair_revisions (pair_id, pair_revision),
        FOREIGN KEY (project_id, pin_revision)
            REFERENCES project_pin_revisions (project_id, pin_revision))""",
    f"""CREATE TABLE diagnostic_snapshots (
        snapshot_id TEXT PRIMARY KEY {_UUID.format("snapshot_id")},
        analysis_id TEXT NOT NULL UNIQUE REFERENCES analysis_runs (analysis_id),
        content_sha256 TEXT NOT NULL {_SHA.format("content_sha256")}, {_DOC})""",
    f"""CREATE TABLE enrichment_runs (
        enrichment_id TEXT PRIMARY KEY {_UUID.format("enrichment_id")},
        analysis_id TEXT NOT NULL UNIQUE REFERENCES analysis_runs (analysis_id),
        snapshot_id TEXT NOT NULL REFERENCES diagnostic_snapshots (snapshot_id), {_DOC})""",
    f"""CREATE TABLE context_cache (
        cache_key TEXT PRIMARY KEY {_SHA.format("cache_key")},
        analysis_id TEXT NOT NULL REFERENCES analysis_runs (analysis_id), {_DOC})""",
    """CREATE TABLE commands (
        command_id TEXT PRIMARY KEY,
        namespace TEXT NOT NULL CHECK (namespace IN ('curation', 'operations')),
        operation TEXT NOT NULL,
        payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
        actor_context_id TEXT NOT NULL REFERENCES actor_contexts (actor_context_id),
        record_ref TEXT NOT NULL,
        state TEXT NOT NULL CHECK (state IN ('in_progress', 'completed', 'abandoned')),
        receipt TEXT, receipt_sha256 TEXT,
        CHECK ((receipt IS NULL) = (receipt_sha256 IS NULL)))""",
    """CREATE TABLE events (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        namespace TEXT NOT NULL CHECK (namespace IN ('curation', 'operations')),
        payload TEXT NOT NULL,
        payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64))""",
    f"""CREATE TABLE curation_records (
        kind TEXT NOT NULL CHECK (kind IN ({", ".join(f"'{k}'" for k in CURATION_KINDS)})),
        record_key TEXT NOT NULL,
        version INTEGER NOT NULL CHECK (version >= 1),
        payload TEXT NOT NULL,
        payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
        PRIMARY KEY (kind, record_key))""",
    "CREATE VIEW curation_events AS "
    "SELECT seq, payload, payload_sha256 FROM events WHERE namespace = 'curation'",
)

_IMMUTABLE_TABLES = (
    "actor_contexts",
    "models",
    "source_revisions",
    "pair_revisions",
    "catalog_releases",
    "project_pin_revisions",
    "adoption_plans",
    "diagnostic_snapshots",
    "enrichment_runs",
    "context_cache",
    "events",
)
_MUTABLE_KEYS = {
    "projects": "project_id",
    "source_heads": "source_id",
    "project_pair_heads": "pair_id",
    "project_pin_heads": "project_id",
    "analysis_runs": "analysis_id, project_id, pair_id, pair_revision, pin_revision, "
    "identity_sha256, parent_analysis_id",
    "curation_records": "kind, record_key",
    "commands": "command_id, namespace, operation, payload_sha256, actor_context_id, record_ref",
}


def _triggers_v1() -> tuple[str, ...]:
    statements: list[str] = []
    for table in (*_IMMUTABLE_TABLES, *_MUTABLE_KEYS):
        statements.append(
            f"CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table} "
            f"BEGIN SELECT RAISE(ABORT, '{table}: exclusão proibida'); END"
        )
    for table in _IMMUTABLE_TABLES:
        statements.append(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE ON {table} "
            f"BEGIN SELECT RAISE(ABORT, '{table}: registro imutável'); END"
        )
    for table, keys in _MUTABLE_KEYS.items():
        # Dispara só quando um valor de identidade muda: o CAS reescreve essas colunas
        # com o mesmo valor ao trocar estado/payload.
        changed = " OR ".join(f"OLD.{key} IS NOT NEW.{key}" for key in keys.split(", "))
        statements.append(
            f"CREATE TRIGGER {table}_identity BEFORE UPDATE OF {keys} ON {table} "
            f"WHEN {changed} "
            f"BEGIN SELECT RAISE(ABORT, '{table}: identidade imutável'); END"
        )
    statements.append(
        "CREATE TRIGGER analysis_runs_terminal BEFORE UPDATE ON analysis_runs "
        "WHEN OLD.state IN ('completed', 'failed', 'interrupted') "
        "BEGIN SELECT RAISE(ABORT, 'analysis_runs: run terminal é imutável'); END"
    )
    statements.append(
        "CREATE TRIGGER commands_terminal BEFORE UPDATE ON commands "
        "WHEN OLD.state <> 'in_progress' "
        "BEGIN SELECT RAISE(ABORT, 'commands: comando terminal é imutável'); END"
    )
    return tuple(statements)


MIGRATIONS: tuple[tuple[str, ...], ...] = ((*_TABLES_V1, *_triggers_v1()),)
"""Migrações numeradas a partir de 1; cada uma roda inteira numa transação."""

SCHEMA_VERSION: Final = len(MIGRATIONS)


class OperationalUnitOfWork:
    """Repositórios ligados à mesma conexão e à mesma transação ``BEGIN IMMEDIATE``."""

    def __init__(self, connection: sqlite3.Connection, store: "OperationalStore") -> None:
        """Monta os repositórios; nenhum deles confirma a transação."""
        self._connection = connection
        self.purpose: StorePurpose = store.purpose
        self.installation_id: str = store.installation_id
        self.actors = Table(connection, ACTOR_CONTEXTS)
        self.projects = Table(connection, PROJECTS)
        self.models = Table(connection, MODELS)
        self.sources = VersionedRepository(connection, SOURCE_REVISIONS, SOURCE_HEADS)
        self.pairs = VersionedRepository(connection, PAIR_REVISIONS, PAIR_HEADS)
        self.releases = ReleaseRepository(connection, CATALOG_RELEASES)
        self.pins = VersionedRepository(connection, PIN_REVISIONS, PIN_HEADS)
        self.adoption_plans = Table(connection, ADOPTION_PLANS)
        self.analyses = Table(connection, ANALYSIS_RUNS)
        self.diagnostics = Table(connection, DIAGNOSTIC_SNAPSHOTS)
        self.enrichments = Table(connection, ENRICHMENT_RUNS)
        self.cache = Table(connection, CONTEXT_CACHE)
        self.commands = CommandRepository(connection)
        self.events = EventRepository(connection)
        self.curation = CurationRecordRepository(connection)

    @property
    def connection(self) -> sqlite3.Connection:
        """Conexão da transação, para consultas de diagnóstico (pragmas)."""
        return self._connection


class OperationalStore:
    """Autoridade operacional local: um banco, propósito fixo, transações serializáveis."""

    def __init__(
        self,
        root: Path,
        *,
        purpose: StorePurpose,
        installation_id: str,
        busy_timeout_ms: int,
    ) -> None:
        """Use ``OperationalStore.open``; o construtor não toca o disco."""
        self.root = root
        self.path = root / DB_FILE
        self.purpose: StorePurpose = purpose
        self.installation_id = installation_id
        self.schema_version = SCHEMA_VERSION
        self._busy_timeout_ms = busy_timeout_ms

    @classmethod
    def open(
        cls,
        root: Path,
        *,
        purpose: StorePurpose | None = None,
        busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
    ) -> "OperationalStore":
        """Cria (com ``purpose``) ou abre o banco; nunca recupera análises nem toma lock."""
        if purpose is not None and purpose not in get_args(StorePurpose):
            raise StorePurposeError(f"purpose inválido: {purpose!r}")
        if busy_timeout_ms < 1:
            raise ValueError("busy_timeout_ms precisa ser positivo")
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StoreUnavailableError(f"raiz do banco inacessível: {exc}") from exc
        store = cls(
            root,
            purpose=purpose or "operational",
            installation_id="",
            busy_timeout_ms=busy_timeout_ms,
        )
        connection = store._connect()
        try:
            store._migrate(connection, purpose)
        finally:
            connection.close()
        return store

    def _migrate(self, connection: sqlite3.Connection, purpose: StorePurpose | None) -> None:
        try:
            connection.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as exc:
            raise sqlite_failure(exc, "abrir banco") from exc
        try:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise StoreSchemaError(
                    f"schema {version} é mais novo que o suportado ({SCHEMA_VERSION})"
                )
            if version == 0:
                tables = connection.execute(
                    "SELECT count(*) FROM sqlite_master WHERE type = 'table'"
                ).fetchone()[0]
                if tables:
                    raise StoreSchemaError("schema desconhecido: tabelas sem versão registrada")
                if purpose is None:
                    raise StorePurposeError("purpose obrigatório ao criar o banco operacional")
            for number in range(version, SCHEMA_VERSION):
                for statement in MIGRATIONS[number]:
                    connection.execute(statement)
                if number == 0:
                    connection.executemany(
                        "INSERT INTO store_metadata (key, value) VALUES (?, ?)",
                        (
                            ("purpose", purpose or ""),
                            ("installation_id", str(uuid.uuid4())),
                            ("created_at_utc", utc_now()),
                        ),
                    )
                connection.execute(f"PRAGMA user_version = {number + 1}")
            metadata = dict(connection.execute("SELECT key, value FROM store_metadata"))
            stored = metadata.get("purpose")
            if stored not in get_args(StorePurpose):
                raise StoreIntegrityError(f"integrity: purpose gravado inválido: {stored!r}")
            if purpose is not None and purpose != stored:
                raise StorePurposeError(
                    f"purpose imutável: banco criado como {stored}, pedido {purpose}"
                )
            self.purpose = stored  # type: ignore[assignment]
            self.installation_id = metadata["installation_id"]
            connection.execute("COMMIT")
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise

    def _connect(self) -> sqlite3.Connection:
        try:
            connection = sqlite3.connect(
                self.path, isolation_level=None, timeout=self._busy_timeout_ms / 1000
            )
        except sqlite3.Error as exc:
            raise sqlite_failure(exc, "conectar") from exc
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            mode = connection.execute("PRAGMA journal_mode = WAL").fetchone()[0]
            if str(mode).lower() != "wal":
                raise StoreUnavailableError(f"journal_mode WAL indisponível ({mode})")
            connection.execute("PRAGMA synchronous = FULL")
            connection.execute(f"PRAGMA busy_timeout = {int(self._busy_timeout_ms)}")
        except sqlite3.Error as exc:
            connection.close()
            raise sqlite_failure(exc, "configurar conexão") from exc
        except BaseException:
            connection.close()
            raise
        return connection

    @contextmanager
    def transaction(self) -> Iterator[OperationalUnitOfWork]:
        """Confirma tudo junto na saída normal; qualquer exceção desfaz a transação inteira.

        Erros do corpo saem como foram lançados (depois do rollback); falhas de início
        e de commit saem tipadas (``StoreBusyError``/``StoreUnavailableError``).
        """
        connection = self._connect()
        try:
            try:
                connection.execute("BEGIN IMMEDIATE")
            except sqlite3.Error as exc:
                raise sqlite_failure(exc, "iniciar transação") from exc
            try:
                yield OperationalUnitOfWork(connection, self)
            except BaseException:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
            try:
                connection.execute("COMMIT")
            except sqlite3.Error as exc:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise sqlite_failure(exc, "confirmar transação") from exc
        finally:
            connection.close()
