"""Persistência local dos projetos da API de revisão — PROVISÓRIO.

SQLite da biblioteca padrão em ``<data_root>/m4_projects.sqlite3``, como a M6
prevê para a persistência local (§ base técnica: sqlite3, um coordenador
escritor). Guarda só o documento ``Project`` e as datas; os bytes continuam em
``blobs/`` endereçados por SHA-256. O esquema definitivo, migrações, sessões e
recibos são da M4-12/M6; esta tabela existe para "abrir projeto existente".

O ``ProjectRegistry`` é o único escritor (serializado pelo lock dele).

Concorre com o ``OperationalStore`` (``operations.sqlite3``) do Felipe, em
``origin/codex/m1-domain-catalog``; a proposta é aposentar esta tabela quando a
``review_api`` virar fachada do ``ProjectService`` (ver
``docs/planejamento/apoios-modulo-04/integracao-m2-m3.md``).
"""

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger
from pydantic import ValidationError

from src.review_api.schemas import Project

DB_FILENAME = "m4_projects.sqlite3"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    document TEXT NOT NULL
)
"""


def utc_now() -> datetime:
    """Instante atual em UTC (relógio do servidor local)."""
    return datetime.now(UTC)


@dataclass(frozen=True)
class StoredProject:
    """Projeto persistido com as datas de criação e da última alteração."""

    project: Project
    created_at: datetime
    updated_at: datetime


class ProjectStore:
    """Tabela única de projetos; cada gravação é uma transação curta."""

    def __init__(self, data_root: Path) -> None:
        """Cria (se preciso) o banco e a tabela sob a raiz de dados."""
        data_root.mkdir(parents=True, exist_ok=True)
        self.path = data_root / DB_FILENAME
        with closing(self._connect()) as conn, conn:
            conn.execute(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        """Abre conexão nova (uma por operação; sem compartilhar entre threads)."""
        return sqlite3.connect(self.path, timeout=5.0)

    def load_all(self) -> list[StoredProject]:
        """Lê todos os projetos válidos; linha corrompida é ignorada com aviso."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT project_id, created_at, updated_at, document FROM projects"
            ).fetchall()
        stored: list[StoredProject] = []
        for project_id, created_at, updated_at, document in rows:
            try:
                project = Project.model_validate_json(document)
                stored.append(
                    StoredProject(
                        project=project,
                        created_at=datetime.fromisoformat(created_at),
                        updated_at=datetime.fromisoformat(updated_at),
                    )
                )
            except (ValidationError, ValueError):
                logger.warning("Projeto {} ignorado: documento inválido no banco local", project_id)
        return stored

    def save(self, project: Project, created_at: datetime, updated_at: datetime) -> None:
        """Insere ou substitui o documento do projeto."""
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO projects (project_id, name, created_at, updated_at, document) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(project_id) DO UPDATE SET name = excluded.name, "
                "updated_at = excluded.updated_at, document = excluded.document",
                (
                    project.project_id,
                    project.name,
                    created_at.isoformat(),
                    updated_at.isoformat(),
                    project.model_dump_json(),
                ),
            )
