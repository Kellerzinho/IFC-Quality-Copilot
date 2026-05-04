"""Rastreabilidade de decisões do engenheiro sobre correções IFC."""

import csv
import threading
from typing import Any, Literal
from uuid import uuid4

from loguru import logger

from src.models import AuditEntry

_CSV_FIELDNAMES = [
    "timestamp", "session_id", "element_guid", "element_class",
    "action", "field", "old_value", "new_value",
    "decision", "confidence", "normative_ref", "source", "user",
    "grounding_mode", "grounding_sources", "bsdd_uri",
    "ids_requirement_id", "post_validation", "prompt_hash",
]


class AuditLogger:
    """Registra todas as decisões do engenheiro para rastreabilidade."""

    def __init__(self, session_id: str | None = None, model_name: str = "") -> None:
        self.session_id = session_id or str(uuid4())[:12]
        self.model_name = model_name
        self.entries: list[AuditEntry] = []
        self._lock = threading.Lock()
        logger.info(
            "AuditLogger iniciado: session={}, modelo={}", self.session_id, self.model_name
        )

    def log(self, entry: AuditEntry) -> None:
        """Adiciona uma entrada de auditoria com o session_id da sessão atual."""
        with self._lock:
            entry.session_id = self.session_id
            self.entries.append(entry)
            logger.debug(
                "Audit: {} em {} → {}", entry.action, entry.element_guid, entry.new_value
            )

    def log_simples(
        self,
        guid: str,
        acao: str,
        valor_anterior: Any,
        valor_novo: Any,
        decisao: Literal["accepted", "edited", "rejected"],
        referencia: str | None = None,
        usuario: str = "engineer",
        element_class: str = "unknown",
    ) -> None:
        """Registra entrada simplificada sem exigir field, confidence ou source."""
        entry = AuditEntry(
            element_guid=guid,
            element_class=element_class,
            action=acao,
            field="",
            old_value=valor_anterior,
            new_value=valor_novo,
            decision=decisao,
            confidence="media",
            normative_ref=referencia,
            source="llm",
            user=usuario,
        )
        self.log(entry)

    def export_csv(self, filepath: str) -> str:
        """Exporta o log de auditoria como CSV.

        Colunas na ordem definida por AuditEntry.to_csv_row().
        Retorna o caminho do arquivo criado.
        """
        with self._lock:
            snapshot = list(self.entries)

        with open(filepath, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=_CSV_FIELDNAMES)
            writer.writeheader()
            for entry in snapshot:
                writer.writerow(entry.to_csv_row())

        logger.info("AuditLogger: CSV exportado → {} ({} entradas)", filepath, len(snapshot))
        return filepath

    def export_json(self, filepath: str) -> str:
        """Exporta o log de auditoria como JSON Lines (uma entrada por linha).

        Retorna o caminho do arquivo criado.
        """
        with self._lock:
            snapshot = list(self.entries)

        with open(filepath, "w", encoding="utf-8") as fh:
            for entry in snapshot:
                fh.write(entry.model_dump_json(by_alias=False) + "\n")

        logger.info(
            "AuditLogger: JSON Lines exportado → {} ({} entradas)", filepath, len(snapshot)
        )
        return filepath

    def get_summary(self) -> dict:
        """Retorna resumo estatístico das entradas de auditoria.

        Campos retornados:
            total_entries, accepted, edited, rejected,
            by_action, by_confidence, by_source
        """
        with self._lock:
            snapshot = list(self.entries)

        summary: dict = {
            "total_entries": len(snapshot),
            "accepted": 0,
            "edited": 0,
            "rejected": 0,
            "by_action": {},
            "by_confidence": {},
            "by_source": {},
        }

        for entry in snapshot:
            if entry.decision == "accepted":
                summary["accepted"] += 1
            elif entry.decision == "edited":
                summary["edited"] += 1
            elif entry.decision == "rejected":
                summary["rejected"] += 1

            summary["by_action"][entry.action] = summary["by_action"].get(entry.action, 0) + 1
            summary["by_confidence"][entry.confidence] = (
                summary["by_confidence"].get(entry.confidence, 0) + 1
            )
            summary["by_source"][entry.source] = summary["by_source"].get(entry.source, 0) + 1

        return summary

    def get_entries_for_element(self, guid: str) -> list[AuditEntry]:
        """Retorna o histórico de decisões para um elemento específico pelo GUID."""
        with self._lock:
            return [e for e in self.entries if e.element_guid == guid]

    def clear(self) -> None:
        """Limpa todas as entradas do log (uso em testes)."""
        with self._lock:
            self.entries.clear()
        logger.debug("AuditLogger: log limpo (session={})", self.session_id)
