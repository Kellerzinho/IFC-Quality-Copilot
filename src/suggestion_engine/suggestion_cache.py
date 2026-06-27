"""Cache persistente de sugestões via SQLite.

A assinatura de cache combina (model_version, prompt_version, issue_type,
ifc_class, target_pset, target_property, expected_type, expected_unit,
requirement_id, candidatos oficiais, hash do contexto normalizado).

Invalidação é feita por mudança de model_version ou prompt_version.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from src.models import Suggestion

PROMPT_VERSION = "v2"


def compute_signature(
    *,
    model_version: str,
    prompt_version: str,
    issue_type: str,
    ifc_class: str,
    target_pset: str | None,
    target_property: str | None,
    expected_type: str | None,
    expected_unit: str | None,
    requirement_id: str | None,
    candidates: list[str] | None,
    context_payload: dict | None = None,
) -> str:
    """Gera assinatura SHA256 estável para cache lookup."""
    sorted_candidates = sorted(candidates or [])
    if context_payload is None:
        context_payload = {}
    context_norm = json.dumps(context_payload, sort_keys=True, ensure_ascii=False, default=str)
    parts = [
        model_version,
        prompt_version,
        issue_type,
        ifc_class,
        target_pset or "",
        target_property or "",
        expected_type or "",
        expected_unit or "",
        requirement_id or "",
        "|".join(sorted_candidates),
        hashlib.sha256(context_norm.encode("utf-8")).hexdigest()[:16],
    ]
    payload = "::".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class SuggestionCache:
    """Cache SQLite leve para sugestões geradas pelo LLM."""

    def __init__(self, db_path: str | Path) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        """Cria a tabela se não existir."""
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS suggestion_cache (
                    signature TEXT PRIMARY KEY,
                    model_version TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cache_versions ON suggestion_cache(model_version, prompt_version)"
            )

    def get(self, signature: str) -> list[Suggestion] | None:
        """Retorna sugestões em cache para a assinatura, ou None se ausente."""
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM suggestion_cache WHERE signature = ?",
                (signature,),
            ).fetchone()
        if row is None:
            return None
        try:
            data = json.loads(row[0])
            return [Suggestion.model_validate(item) for item in data]
        except Exception as exc:
            logger.warning("Cache: payload corrompido para {}: {}", signature[:12], exc)
            return None

    def set(
        self,
        signature: str,
        suggestions: list[Suggestion],
        model_version: str,
        prompt_version: str,
    ) -> None:
        """Armazena sugestões para a assinatura (substitui se já existir)."""
        if not suggestions:
            return
        payload = json.dumps(
            [s.model_dump(mode="json") for s in suggestions],
            ensure_ascii=False,
        )
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO suggestion_cache
                (signature, model_version, prompt_version, payload, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (signature, model_version, prompt_version, payload, datetime.now().isoformat()),
            )

    def invalidate_by_model(self, current_model_version: str) -> int:
        """Remove entradas de modelos antigos. Retorna quantas linhas removidas."""
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM suggestion_cache WHERE model_version != ?",
                (current_model_version,),
            )
            return cursor.rowcount

    def invalidate_by_prompt(self, current_prompt_version: str) -> int:
        """Remove entradas de prompt versions antigas."""
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM suggestion_cache WHERE prompt_version != ?",
                (current_prompt_version,),
            )
            return cursor.rowcount

    def size(self) -> int:
        """Retorna número de entradas no cache."""
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) FROM suggestion_cache").fetchone()
        return int(row[0]) if row else 0

    def clear(self) -> None:
        """Remove todas entradas do cache."""
        with self._lock:
            self._conn.execute("DELETE FROM suggestion_cache")

    def close(self) -> None:
        """Fecha a conexão SQLite."""
        with self._lock:
            self._conn.close()
