"""Cópia de segurança local e restauração isolada da área operacional (ensaio M1-16).

Procedimento mínimo para **um processo, disco local e Windows/NTFS**, ensaiado com dados
sintéticos. Não é a política de backup da M6 (retenção, agendamento, cifra, cópia fora
do equipamento e multiusuário continuam decisões abertas da frente 6).

Corte coerente: o banco é copiado primeiro pela API de backup online do SQLite (um
snapshot transacional consistente, também em WAL); depois os artefatos sob ``a/``.
Artefatos são imutáveis depois de registrados, então a pasta copiada é superconjunto
do que o banco cita; bytes sem registro (preparo interrompido) aparecem na inspeção de
publicação como não registrados e nunca viram release. Copiar os artefatos antes do
banco poderia deixar o banco citando bytes ausentes, por isso a ordem é fixa.

A restauração só escreve numa pasta nova e vazia, confere cada hash do manifesto e a
integridade do SQLite antes e depois da cópia. Nunca sobrescreve a área de origem.
"""

import hashlib
import os
import shutil
import sqlite3
from pathlib import Path
from typing import Final, Literal

from pydantic import Field

from src.domain_catalog.canonical import canonical_json_bytes, parse_json_strict
from src.domain_catalog.contracts import ContractModel
from src.domain_catalog.curation import utc_now
from src.operations.database import DB_FILE

BACKUP_FORMAT: Final = "ifcqc-local-backup"
MANIFEST_NAME = "backup-manifest.json"
DB_DIR = "db"
ARTIFACTS_DIR = "a"


class BackupError(Exception):
    """Cópia ou restauração recusada; nenhuma área existente foi alterada."""

    code = "backup_error"


class BackupFile(ContractModel):
    """Arquivo copiado: caminho relativo (``/``), tamanho e SHA-256 dos bytes."""

    path: str
    size_bytes: int = Field(ge=0)
    sha256: str


class BackupManifest(ContractModel):
    """Manifesto da cópia; não guarda caminhos absolutos da instalação."""

    format: Literal["ifcqc-local-backup"] = BACKUP_FORMAT
    format_version: Literal[1] = 1
    created_at_utc: str
    db_file: Literal["db/operations.sqlite3"]
    db_integrity: Literal["ok"]
    files: tuple[BackupFile, ...]
    guarantee: str = (
        "processo único, disco local Windows/NTFS; sem garantia para rede, "
        "multiusuário ou cópia concorrente com escrita de artefatos"
    )
    authenticity: str = (
        "hashes detectam corrupção acidental; o manifesto não é assinado e não prova "
        "autoria nem ausência de adulteração deliberada"
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_empty_new(target: Path, label: str, *, outside: Path) -> None:
    if target.is_symlink() or (target.exists() and any(target.iterdir())):
        raise BackupError(f"{label}: exige pasta nova e vazia; nada foi escrito")
    resolved, other = target.resolve(), outside.resolve()
    if resolved.is_relative_to(other) or other.is_relative_to(resolved):
        raise BackupError(f"{label}: não pode ficar dentro da origem nem contê-la")


def _integrity(db_path: Path) -> None:
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        result = connection.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        connection.close()
    if result != "ok":
        raise BackupError(f"banco copiado não passa em integrity_check: {result}")


def _walk(base: Path) -> list[Path]:
    found: list[Path] = []
    for directory, folders, names in os.walk(base, followlinks=False):
        current = Path(directory)
        for name in [*folders, *names]:
            path = current / name
            if path.is_symlink() or (os.name == "nt" and _is_reparse(path)):
                raise BackupError("link ou ponto de reanálise na área; cópia recusada")
        found += [current / name for name in names]
    return sorted(found)


def _is_reparse(path: Path) -> bool:
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return bool(attributes & 0x400)


def _record(base: Path, files: list[Path]) -> tuple[BackupFile, ...]:
    return tuple(
        BackupFile(
            path=file.relative_to(base).as_posix(),
            size_bytes=file.stat().st_size,
            sha256=_sha256(file),
        )
        for file in files
    )


def create_backup(root: Path, destination: Path) -> BackupManifest:
    """Copia ``root/db`` (API de backup do SQLite) e depois ``root/a`` para ``destination``.

    ``destination`` precisa ser nova e vazia. A cópia não toca a área de origem além da
    leitura; falha deixa ``destination`` incompleta e sem manifesto (não restaurável).
    """
    source_db = root / DB_DIR / DB_FILE
    if not source_db.is_file():
        raise BackupError("banco operacional não encontrado na área informada")
    _require_empty_new(destination, "destino da cópia", outside=root)
    (destination / DB_DIR).mkdir(parents=True, exist_ok=True)
    copy_db = destination / DB_DIR / DB_FILE
    source = sqlite3.connect(f"{source_db.resolve().as_uri()}?mode=ro", uri=True)
    target = sqlite3.connect(copy_db)
    try:
        source.backup(target)
        # Cópia autocontida num só arquivo; ao reabrir, OperationalStore volta a WAL.
        target.execute("PRAGMA journal_mode = DELETE")
    finally:
        target.close()
        source.close()
    _integrity(copy_db)
    artifacts = root / ARTIFACTS_DIR
    if artifacts.exists():
        for file in _walk(artifacts):
            out = destination / ARTIFACTS_DIR / file.relative_to(artifacts)
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(file, out)
    manifest = BackupManifest(
        created_at_utc=utc_now(),
        db_file="db/operations.sqlite3",
        db_integrity="ok",
        files=_record(destination, _walk(destination)),
    )
    (destination / MANIFEST_NAME).write_bytes(
        canonical_json_bytes(manifest.model_dump(mode="json"))
    )
    return manifest


def verify_backup(backup: Path) -> BackupManifest:
    """Reabre o manifesto e confere cada arquivo e a integridade do banco copiado."""
    manifest_path = backup / MANIFEST_NAME
    if not manifest_path.is_file():
        raise BackupError("cópia sem manifesto: incompleta ou inválida")
    try:
        raw = manifest_path.read_bytes().decode("utf-8")
        manifest = BackupManifest.model_validate(parse_json_strict(raw))
    except Exception as exc:
        raise BackupError(f"manifesto ilegível: {type(exc).__name__}") from exc
    listed = {entry.path for entry in manifest.files}
    present = {
        file.relative_to(backup).as_posix() for file in _walk(backup) if file != manifest_path
    }
    if listed != present:
        raise BackupError(
            f"arquivos divergem do manifesto: faltam {sorted(listed - present)[:5]}, "
            f"sobram {sorted(present - listed)[:5]}"
        )
    for entry in manifest.files:
        file = backup / entry.path
        if file.stat().st_size != entry.size_bytes or _sha256(file) != entry.sha256:
            raise BackupError(f"hash divergente: {entry.path}")
    _integrity(backup / manifest.db_file)
    return manifest


def restore_backup(backup: Path, target: Path) -> BackupManifest:
    """Restaura numa pasta nova e vazia, conferindo hashes antes e depois."""
    manifest = verify_backup(backup)
    _require_empty_new(target, "destino da restauração", outside=backup)
    for entry in manifest.files:
        out = target / entry.path
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(backup / entry.path, out)
    for entry in manifest.files:
        if _sha256(target / entry.path) != entry.sha256:
            raise BackupError(f"hash divergente após restaurar: {entry.path}")
    _integrity(target / manifest.db_file)
    return manifest
