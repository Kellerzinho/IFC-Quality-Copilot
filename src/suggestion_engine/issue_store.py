"""Armazena issues com status de geração de sugestão para processamento progressivo."""

import threading
from collections import deque
from typing import Literal

from loguru import logger

from src.models import Issue, SuggestionSet

IssueStatus = Literal[
    "queued",
    "processing",
    "ready",
    "cached",
    "reused",
    "invalid",
    "failed",
    "review_required",
    "cancelled",
]

_TERMINAL_STATUSES: set[str] = {
    "ready",
    "cached",
    "reused",
    "invalid",
    "failed",
    "review_required",
    "cancelled",
}

_PENDING_STATUSES: set[str] = {"queued", "processing"}

_SEVERITY_ORDER: dict[str, int] = {"high": 0, "medium": 1, "low": 2}


class IssueStore:
    """Armazena issues com status de geração de sugestão para processamento progressivo."""

    def __init__(self, max_concurrent: int = 1) -> None:
        self._issues: dict[str, Issue] = {}
        self._suggestions: dict[str, SuggestionSet | None] = {}
        self._status: dict[str, IssueStatus] = {}
        self._reuse_origin: dict[str, str] = {}
        self._order: list[str] = []
        self._order_set: set[str] = set()
        self._queue: deque[str] = deque()
        self._counts: dict[str, int] = {
            "queued": 0,
            "processing": 0,
            "ready": 0,
            "cached": 0,
            "reused": 0,
            "invalid": 0,
            "failed": 0,
            "review_required": 0,
            "cancelled": 0,
        }
        self._lock = threading.Lock()
        self._max_concurrent = max(1, int(max_concurrent))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _set_status(self, issue_id: str, new_status: IssueStatus) -> None:
        """Atualiza status mantendo contadores. Deve ser chamado dentro do lock."""
        old = self._status.get(issue_id)
        if old == new_status:
            return
        if old is not None and old in self._counts:
            self._counts[old] -= 1
        self._status[issue_id] = new_status
        if new_status in self._counts:
            self._counts[new_status] += 1

    # ------------------------------------------------------------------
    # Adicionar / consultar
    # ------------------------------------------------------------------

    def add_issues(
        self,
        issues: list[Issue],
        priority_issue_types: list[str] | None = None,
    ) -> None:
        """Adiciona issues e ordena por prioridade.

        priority_issue_types: tipos vêm primeiro. Dentro de cada grupo, ordena
        por severity (high → medium → low). Status inicial: 'queued'.
        """
        priority_types = set(priority_issue_types or [])
        priority_group: list[Issue] = []
        normal_group: list[Issue] = []
        for issue in issues:
            if issue.issue_type in priority_types:
                priority_group.append(issue)
            else:
                normal_group.append(issue)

        priority_group.sort(key=lambda i: _SEVERITY_ORDER[i.severity])
        normal_group.sort(key=lambda i: _SEVERITY_ORDER[i.severity])
        ordered = priority_group + normal_group

        with self._lock:
            for issue in ordered:
                was_known = issue.id in self._order_set
                old_status = self._status.get(issue.id)
                self._issues[issue.id] = issue
                self._suggestions[issue.id] = None
                self._set_status(issue.id, "queued")
                if not was_known:
                    self._order.append(issue.id)
                    self._order_set.add(issue.id)
                if not was_known or old_status != "queued":
                    self._queue.append(issue.id)

        logger.debug("IssueStore: {} issues adicionados ({} prioritários)", len(issues), len(priority_group))

    # ------------------------------------------------------------------
    # Transições
    # ------------------------------------------------------------------

    def can_accept_processing(self) -> bool:
        """True se há slot livre para iniciar uma nova chamada LLM (backpressure)."""
        with self._lock:
            return self._counts["processing"] < self._max_concurrent

    def mark_processing(self, issue_id: str) -> None:
        """Marca issue como em processamento pelo LLM."""
        with self._lock:
            self._set_status(issue_id, "processing")

    def mark_ready(self, issue_id: str, suggestion_set: SuggestionSet) -> None:
        """Marca issue como pronta (sugestão LLM chegou)."""
        with self._lock:
            self._suggestions[issue_id] = suggestion_set
            self._set_status(issue_id, "ready")

    def mark_cached(self, issue_id: str, suggestion_set: SuggestionSet) -> None:
        """Marca issue como cache hit."""
        with self._lock:
            self._suggestions[issue_id] = suggestion_set
            self._set_status(issue_id, "cached")

    def mark_reused(self, issue_id: str, suggestion_set: SuggestionSet, from_issue_id: str) -> None:
        """Marca issue como reusada de outra issue equivalente."""
        with self._lock:
            self._suggestions[issue_id] = suggestion_set
            self._reuse_origin[issue_id] = from_issue_id
            self._set_status(issue_id, "reused")

    def mark_review_required(self, issue_id: str, suggestion_set: SuggestionSet | None = None) -> None:
        """Marca issue exigindo revisão humana (sem grounding confiável)."""
        with self._lock:
            if suggestion_set is not None:
                self._suggestions[issue_id] = suggestion_set
            self._set_status(issue_id, "review_required")

    def mark_invalid(self, issue_id: str, error: str) -> None:
        """Marca issue como inválida (falha de schema/validação)."""
        with self._lock:
            self._set_status(issue_id, "invalid")
            self._suggestions[issue_id] = SuggestionSet(
                issue_id=issue_id,
                suggestions=[],
                error=error,
            )

    def mark_failed(self, issue_id: str, error: str) -> None:
        """Marca issue como falha (exceção / timeout)."""
        with self._lock:
            self._set_status(issue_id, "failed")
            self._suggestions[issue_id] = SuggestionSet(issue_id=issue_id, suggestions=[], error=error)
        logger.warning("IssueStore: issue {} falhou: {}", issue_id, error)

    def cancel(self, issue_id: str) -> None:
        """Cancela uma issue (remove processamento subsequente)."""
        with self._lock:
            if self._status.get(issue_id) in _PENDING_STATUSES:
                self._set_status(issue_id, "cancelled")

    def requeue(self, issue_id: str) -> None:
        """Recoloca issue na fila para reprocessamento."""
        with self._lock:
            self._set_status(issue_id, "queued")
            self._suggestions[issue_id] = None
            self._reuse_origin.pop(issue_id, None)
            self._queue.appendleft(issue_id)
        logger.debug("IssueStore: issue {} recolocada na fila", issue_id)

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    def get_issue(self, issue_id: str) -> Issue | None:
        """Retorna a Issue pelo id, ou None se não existe."""
        with self._lock:
            return self._issues.get(issue_id)

    def get_suggestion(self, issue_id: str) -> SuggestionSet | None:
        """Retorna o SuggestionSet armazenado para a issue."""
        with self._lock:
            return self._suggestions.get(issue_id)

    def get_status(self, issue_id: str) -> IssueStatus | None:
        with self._lock:
            return self._status.get(issue_id)

    def get_next_queued(self) -> str | None:
        """Retorna o próximo issue_id com status 'queued', respeitando prioridade."""
        with self._lock:
            while self._queue:
                issue_id = self._queue.popleft()
                if self._status.get(issue_id) == "queued":
                    return issue_id
        return None

    def get_ready_issues(self) -> list[tuple[Issue, SuggestionSet]]:
        """Retorna issues com sugestão disponível (ready/cached/reused)."""
        with self._lock:
            result = []
            for issue_id in self._order:
                status = self._status.get(issue_id)
                if status in {"ready", "cached", "reused", "review_required"}:
                    sset = self._suggestions[issue_id]
                    if sset is not None:
                        result.append((self._issues[issue_id], sset))
            return result

    def get_all_with_status(self) -> list[dict]:
        """Retorna lista de {issue, suggestion, status, reused_from} para a UI."""
        with self._lock:
            return [
                {
                    "issue": self._issues[issue_id],
                    "suggestion": self._suggestions.get(issue_id),
                    "status": self._status.get(issue_id, "queued"),
                    "reused_from": self._reuse_origin.get(issue_id),
                }
                for issue_id in self._order
            ]

    def get_progress(self) -> dict:
        """Retorna contagens por status + percent_complete.

        percent_complete = (qualquer status terminal) / total * 100
        """
        with self._lock:
            counts = dict(self._counts)
            total = len(self._order)
            done = sum(self._counts[s] for s in _TERMINAL_STATUSES)
            percent = (done / total * 100) if total > 0 else 0.0

            return {
                "total": total,
                **counts,
                "percent_complete": round(percent, 1),
            }

    def get_counts_by_status(self) -> dict[str, int]:
        """Retorna apenas o mapa de contagens por status."""
        with self._lock:
            return dict(self._counts)

    def is_all_done(self) -> bool:
        """True quando nenhuma issue está queued ou processing."""
        with self._lock:
            return all(s not in _PENDING_STATUSES for s in self._status.values())
