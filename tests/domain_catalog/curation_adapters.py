"""ADAPTADORES DE TESTE da E2 — NÃO OPERACIONAIS.

Fazem o papel das portas que o M6 ainda não implementou (ator local, persistência
transacional e armazenamento de releases), só para exercitar a curadoria e a
publicação em pastas temporárias. Não são integração de produção, não definem o
banco do M6 e não são importados por ``src``: cada adaptador declara
``operational = False``, valor que aparece nos recibos.

Os contextos de ator são SINTÉTICOS. Um nome como "Pessoa Curadora Sintética" não
representa ninguém; nada do que estes adaptadores gravam é aprovação real de conteúdo.
"""

import json
import os
import re
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from src.domain_catalog.contracts import CatalogReleaseRef
from src.domain_catalog.curation import CurationService
from src.domain_catalog.draft_store import (
    RecordKind,
    StoreConflictError,
    StoredRecord,
    StoreError,
    StoreUnavailableError,
)
from src.domain_catalog.package import MANIFEST_FILE, PackageLimits, ReleaseFiles
from src.domain_catalog.publication import (
    ArtifactStoreError,
    PublicationService,
    ReleaseCollisionError,
    StoreInventory,
    storage_failure,
)

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS records ("
    " kind TEXT NOT NULL, key TEXT NOT NULL, version INTEGER NOT NULL,"
    " document TEXT NOT NULL, PRIMARY KEY (kind, key))",
    "CREATE TABLE IF NOT EXISTS events ("
    " seq INTEGER PRIMARY KEY AUTOINCREMENT, document TEXT NOT NULL)",
)


def _dumps(document: Mapping[str, Any]) -> str:
    try:
        return json.dumps(dict(document), ensure_ascii=False, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise StoreError(f"documento não é JSON: {exc}") from exc


class _SqliteTransaction:
    """Transação aberta com ``BEGIN IMMEDIATE``: um escritor por vez."""

    def __init__(self, connection: sqlite3.Connection, fail_at: set[str]) -> None:
        self._connection = connection
        self._fail_at = fail_at

    def check(self, point: str) -> None:
        """Simula falha de E/S num ponto nomeado do protocolo, se pedido pelo teste."""
        if point in self._fail_at:
            raise StoreUnavailableError(f"falha simulada em {point}")

    def _execute(self, sql: str, parameters: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        try:
            return self._connection.execute(sql, parameters)
        except sqlite3.IntegrityError as exc:
            raise StoreConflictError(f"conflito no armazenamento: {exc}") from exc
        except sqlite3.Error as exc:
            raise StoreUnavailableError(f"falha do armazenamento: {exc}") from exc

    def get(self, kind: RecordKind, key: str) -> StoredRecord | None:
        """Registro pela chave, ou ``None``."""
        row = self._execute(
            "SELECT version, document FROM records WHERE kind = ? AND key = ?", (kind, key)
        ).fetchone()
        if row is None:
            return None
        return StoredRecord(kind=kind, key=key, version=row[0], document=json.loads(row[1]))

    def scan(self, kind: RecordKind) -> tuple[StoredRecord, ...]:
        """Registros do tipo em ordem de chave."""
        rows = self._execute(
            "SELECT key, version, document FROM records WHERE kind = ? ORDER BY key", (kind,)
        ).fetchall()
        return tuple(
            StoredRecord(kind=kind, key=row[0], version=row[1], document=json.loads(row[2]))
            for row in rows
        )

    def insert(self, kind: RecordKind, key: str, document: Mapping[str, Any]) -> StoredRecord:
        """Cria na versão 1; chave existente é conflito."""
        self.check(f"insert:{kind}")
        text = _dumps(document)
        self._execute(
            "INSERT INTO records (kind, key, version, document) VALUES (?, ?, 1, ?)",
            (kind, key, text),
        )
        return StoredRecord(kind=kind, key=key, version=1, document=json.loads(text))

    def replace(
        self, kind: RecordKind, key: str, expected_version: int, document: Mapping[str, Any]
    ) -> StoredRecord:
        """Troca com versão esperada; ausente ou outra versão é conflito."""
        self.check(f"replace:{kind}")
        text = _dumps(document)
        cursor = self._execute(
            "UPDATE records SET version = version + 1, document = ?"
            " WHERE kind = ? AND key = ? AND version = ?",
            (text, kind, key, expected_version),
        )
        if cursor.rowcount != 1:
            current = self.get(kind, key)
            found = "ausente" if current is None else f"versão {current.version}"
            raise StoreConflictError(
                f"{kind} {key}: esperada versão {expected_version}, encontrado {found}"
            )
        return StoredRecord(
            kind=kind, key=key, version=expected_version + 1, document=json.loads(text)
        )

    def append_event(self, document: Mapping[str, Any]) -> int:
        """Acrescenta evento; a sequência vem do banco."""
        self.check("append_event")
        cursor = self._execute("INSERT INTO events (document) VALUES (?)", (_dumps(document),))
        if cursor.lastrowid is None:
            raise StoreUnavailableError("o banco não devolveu a sequência do evento")
        return cursor.lastrowid

    def events(self, after_seq: int = 0) -> tuple[tuple[int, dict[str, Any]], ...]:
        """Eventos confirmados depois da sequência dada."""
        rows = self._execute(
            "SELECT seq, document FROM events WHERE seq > ? ORDER BY seq", (after_seq,)
        ).fetchall()
        return tuple((row[0], json.loads(row[1])) for row in rows)


class SqliteTestCurationStore:
    """``CurationStore`` de TESTE sobre SQLite num arquivo temporário. Não operacional.

    Não é o banco do M6 nem proposta de esquema: guarda documentos JSON genéricos só
    para provar o contrato da porta (transação, conflito, eventos, reabertura).
    ``fail_at`` simula falha de E/S em pontos nomeados (``before_commit``,
    ``insert:<tipo>``, ``replace:<tipo>``, ``append_event``).
    """

    operational = False

    def __init__(self, path: Path, *, fail_at: set[str] | None = None) -> None:
        """Cria as tabelas se o arquivo for novo; reabrir o mesmo arquivo simula reinício."""
        self.path = path
        self.fail_at: set[str] = set(fail_at or ())
        connection = self._connect()
        try:
            for statement in _SCHEMA:
                connection.execute(statement)
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, isolation_level=None, timeout=5.0)
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    @contextmanager
    def transaction(self) -> Iterator[_SqliteTransaction]:
        """Commit na saída normal; qualquer exceção desfaz tudo."""
        try:
            connection = self._connect()
        except sqlite3.Error as exc:
            raise StoreUnavailableError(f"não foi possível abrir o banco de teste: {exc}") from exc
        try:
            connection.execute("BEGIN IMMEDIATE")
            transaction = _SqliteTransaction(connection, self.fail_at)
            try:
                yield transaction
                transaction.check("before_commit")
                connection.execute("COMMIT")
            except BaseException:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
        except sqlite3.Error as exc:
            raise StoreUnavailableError(f"falha transacional no banco de teste: {exc}") from exc
        finally:
            connection.close()


@dataclass(frozen=True)
class SyntheticActorContext:
    """Contexto de ator SINTÉTICO com a forma proposta ao M6."""

    actor_context_id: str
    installation_id: str
    session_id: str
    actor_kind: str
    declared_name: str | None
    identity_assurance: str
    registered_at_utc: str


class SyntheticActorDirectory:
    """Faz o papel do backend que cria e resgata contextos de ator (M6). Só para testes."""

    operational = False

    def __init__(
        self, installation_id: str = "inst-teste", session_id: str = "sessao-teste"
    ) -> None:
        """Diretório vazio de uma instalação e sessão sintéticas."""
        self._installation_id = installation_id
        self._session_id = session_id
        self._contexts: dict[str, SyntheticActorContext] = {}

    def register(
        self,
        actor_kind: str,
        declared_name: str | None,
        *,
        actor_context_id: str | None = None,
        identity_assurance: str = "unverified_local",
        registered_at_utc: str = "2026-10-14T12:00:00Z",
    ) -> str:
        """Registra um contexto e devolve seu ID, como faria o backend."""
        context_id = actor_context_id or f"ctx-{len(self._contexts) + 1:03d}"
        self._contexts[context_id] = SyntheticActorContext(
            actor_context_id=context_id,
            installation_id=self._installation_id,
            session_id=self._session_id,
            actor_kind=actor_kind,
            declared_name=declared_name,
            identity_assurance=identity_assurance,
            registered_at_utc=registered_at_utc,
        )
        return context_id

    def resolve(self, actor_context_id: str) -> SyntheticActorContext | None:
        """Contexto registrado, ou ``None``."""
        return self._contexts.get(actor_context_id)


class TickingClock:
    """Relógio UTC determinístico: cada leitura avança um segundo."""

    def __init__(self, start: str = "2026-10-14T12:00:00Z") -> None:
        """Começa no instante dado."""
        self._now = datetime.strptime(start, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)

    def __call__(self) -> str:
        """Instante atual em UTC; a próxima leitura será um segundo depois."""
        value = self._now.strftime("%Y-%m-%dT%H:%M:%SZ")
        self._now += timedelta(seconds=1)
        return value


class SequentialIds:
    """IDs locais determinísticos (``urn:uuid`` sintéticos)."""

    def __init__(self, prefix: str = "9") -> None:
        """Prefixo hexadecimal distingue fábricas diferentes num mesmo teste."""
        self._prefix = prefix
        self._counter = 0

    def __call__(self) -> str:
        """Próximo ID."""
        self._counter += 1
        return f"urn:uuid:00000000-0000-4000-{self._prefix}000-{self._counter:012d}"


_UUID = re.compile(r"^urn:uuid:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-([0-9a-f]{4})-([0-9a-f]{12})$")
_VERSION = re.compile(r"^\d+\.\d+\.\d+$")


def _short_dir(local_id: str) -> str:
    """Nome de pasta curto e seguro para um ID local: os dois últimos grupos do UUID.

    Curto de propósito: o caminho temporário destes testes no Windows já é longo, e o
    limite de 260 caracteres (sem caminhos longos habilitados) seria excedido. É um
    ponto de atenção registrado para o layout do ``DATA_ROOT`` do M6.
    """
    match = _UUID.match(local_id)
    if match is None:
        raise ArtifactStoreError(f"ID local inválido para pasta: {local_id!r}")
    return match.group(1) + match.group(2)


def _write_durably(path: Path, data: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


class LocalTestReleaseStore:
    """``ReleaseArtifactStore`` de TESTE numa pasta temporária. Não operacional.

    Layout curto: ``s/<candidato>/`` (preparo), ``r/<catálogo>/<versão>/`` (releases) e
    ``q/`` (quarentena). A promoção é uma renomeação exclusiva da pasta de preparo para
    o destino final, que nunca é sobrescrito. A durabilidade no Windows real e o
    diretório operacional (``catalog-authoring/`` do M6) não são certificados aqui.
    ``fail_at`` simula falhas: ``stage``, ``stage_partial`` (grava só o manifesto e
    para), ``stage_corrupt`` (grava um arquivo de dados com um byte a mais),
    ``promote``, ``after_promote`` (promove e então falha) e ``promote_corrupt``
    (promove e acrescenta um byte a um arquivo, como um disco que corrompe na cópia) e
    ``quarantine`` (falha ao mover para a quarentena).

    Cumpre a obrigação de erro da porta: ``OSError`` real (pasta obstruída, acesso
    negado, disco cheio) sai como ``ArtifactStoreError`` com etapa e ``errno``.
    """

    operational = False

    def __init__(self, root: Path, *, fail_at: set[str] | None = None) -> None:
        """Usa ``root`` como raiz das três áreas."""
        self.root = root
        self.fail_at: set[str] = set(fail_at or ())

    def _check(self, point: str) -> None:
        if point in self.fail_at:
            raise ArtifactStoreError(f"falha simulada em {point}")

    def staging_path(self, candidate_id: str) -> Path:
        """Local da pasta de preparo do candidato (pode não existir)."""
        return self.root / "s" / _short_dir(candidate_id)

    def stage(self, candidate_id: str, release: ReleaseFiles) -> Path:
        """Grava os bytes do candidato numa pasta de preparo nova; pasta existente é erro."""
        self._check("stage")
        target = self.staging_path(candidate_id)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                target.mkdir()
            except FileExistsError as exc:
                raise ArtifactStoreError(
                    f"preparo já existe para {candidate_id}", phase="stage", errno=exc.errno
                ) from exc
            _write_durably(target / MANIFEST_FILE, release.manifest_bytes)
            self._check("stage_partial")
            for name, blob in release.data.items():
                corrupt = "stage_corrupt" in self.fail_at and name == "concepts.json"
                _write_durably(target / name, blob + b" " if corrupt else blob)
        except OSError as exc:
            raise storage_failure("stage", exc) from exc
        return target

    def staged_path(self, candidate_id: str) -> Path | None:
        """Pasta de preparo do candidato, se existir (conveniência dos testes)."""
        target = self.staging_path(candidate_id)
        return target if target.is_dir() else None

    def release_path(self, ref: CatalogReleaseRef) -> Path:
        """Destino final do release (pode ainda não existir)."""
        if _VERSION.match(ref.version) is None:
            raise ArtifactStoreError(f"versão inválida para pasta: {ref.version!r}")
        return self.root / "r" / _short_dir(ref.catalog_id) / ref.version

    def promote(self, candidate_id: str, ref: CatalogReleaseRef) -> Path:
        """Renomeia o preparo para o destino final; destino existente nunca é sobrescrito."""
        self._check("promote")
        try:
            source = self.staged_path(candidate_id)
            if source is None:
                raise ArtifactStoreError(f"sem preparo para {candidate_id}", phase="promote")
            target = self.release_path(ref)
            if target.exists():
                raise ReleaseCollisionError(
                    f"destino {target.name} já existe; nada é sobrescrito", phase="promote"
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            os.rename(source, target)
            self._check("after_promote")
            if "promote_corrupt" in self.fail_at:
                damaged = target / "bindings.json"
                damaged.write_bytes(damaged.read_bytes() + b" ")
        except OSError as exc:
            raise storage_failure("promote", exc) from exc
        return target

    def quarantine(self, path: Path, label: str) -> Path:
        """Move a pasta para a quarentena, sem apagar nada."""
        self._check("quarantine")
        area = self.root / "q"
        try:
            area.mkdir(parents=True, exist_ok=True)
            target = area / f"{len(list(area.iterdir())) + 1:03d}-{label}"
            os.rename(path, target)
        except OSError as exc:
            raise storage_failure("quarantine", exc) from exc
        return target

    def inventory(self) -> StoreInventory:
        """Entradas presentes no preparo e na área de releases, inclusive soltas."""
        try:
            return StoreInventory(staged=self.staged_dirs(), releases=self.release_dirs())
        except OSError as exc:
            raise storage_failure("inventory", exc) from exc

    def release_dirs(self) -> tuple[Path, ...]:
        """Entradas da área de releases (publicadas ou não); arquivo solto também conta."""
        area = self.root / "r"
        if not area.is_dir():
            return ()
        return tuple(
            entry
            for catalog in sorted(area.iterdir())
            for entry in (sorted(catalog.iterdir()) if catalog.is_dir() else (catalog,))
        )

    def staged_dirs(self) -> tuple[Path, ...]:
        """Pastas presentes na área de preparo."""
        area = self.root / "s"
        return tuple(sorted(area.iterdir())) if area.is_dir() else ()

    def quarantined(self) -> tuple[Path, ...]:
        """Pastas em quarentena, em ordem."""
        area = self.root / "q"
        return tuple(sorted(area.iterdir())) if area.is_dir() else ()


TEST_LIMITS = PackageLimits(
    max_manifest_bytes=1_048_576, max_file_bytes=1_048_576, max_total_bytes=16_777_216
)
"""Limites menores só para o tempo dos testes: o reader da E1 lê ``limite + 1`` bytes de
uma vez, e com o padrão provisório de 64 MiB cada arquivo custa cerca de 13 ms neste
Windows (medido em 14/10). Os padrões da E1 não mudam; o achado fica registrado na E2."""


@dataclass
class CurationEnv:
    """Curadoria e publicação sobre adaptadores de TESTE, com quatro atores sintéticos."""

    store: SqliteTestCurationStore
    artifacts: LocalTestReleaseStore
    actors: SyntheticActorDirectory
    clock: TickingClock
    new_id: SequentialIds
    curation: CurationService
    publication: PublicationService
    operator: str
    curator: str
    assistant: str
    importer: str


def make_env(
    base: Path,
    *,
    generation: int = 1,
    fail_at: set[str] | None = None,
    artifact_fail_at: set[str] | None = None,
) -> CurationEnv:
    """Ambiente sobre a pasta ``base``; outra geração sobre a mesma pasta simula reinício.

    A geração muda o prefixo dos IDs e o início do relógio, para que registros criados
    depois do reinício não colidam com os anteriores.
    """
    store = SqliteTestCurationStore(base / "c.sqlite3", fail_at=fail_at)
    artifacts = LocalTestReleaseStore(base / "a", fail_at=artifact_fail_at)
    actors = SyntheticActorDirectory()
    operator = actors.register("human", "Pessoa Operadora Sintética")
    curator = actors.register("human", "Pessoa Curadora Sintética")
    assistant = actors.register("assistant", None)
    importer = actors.register("service", None)
    clock = TickingClock(f"2026-10-14T{11 + generation:02d}:00:00Z")
    new_id = SequentialIds(f"{generation:x}")
    publication = PublicationService(
        store, actors, artifacts, clock=clock, new_id=new_id, limits=TEST_LIMITS
    )
    curation = CurationService(store, actors, releases=publication, clock=clock, new_id=new_id)
    return CurationEnv(
        store=store,
        artifacts=artifacts,
        actors=actors,
        clock=clock,
        new_id=new_id,
        curation=curation,
        publication=publication,
        operator=operator,
        curator=curator,
        assistant=assistant,
        importer=importer,
    )
