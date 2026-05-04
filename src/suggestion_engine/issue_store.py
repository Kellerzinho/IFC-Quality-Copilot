"""Armazena issues com status de geração de sugestão para processamento progressivo."""

import threading
from collections import deque
from typing import Literal

from loguru import logger

from src.models import Issue, SuggestionSet

IssueStatus = Literal["queued", "processing", "ready", "failed"]

_SEVERITY_ORDER: dict[str, int] = {"high": 0, "medium": 1, "low": 2}


class IssueStore:
    """Armazena issues com status de geração de sugestão para processamento progressivo."""

    def __init__(self) -> None:
        self._issues: dict[str, Issue] = {}
        self._suggestions: dict[str, SuggestionSet | None] = {}
        self._status: dict[str, IssueStatus] = {}
        self._order: list[str] = []
        self._order_set: set[str] = set()  # O(1) dedup para _order
        self._queue: deque[str] = deque()
        self._counts: dict[str, int] = {
            "queued": 0,
            "processing": 0,
            "ready": 0,
            "failed": 0,
        }
        self._lock = threading.Lock()

    def _set_status(self, issue_id: str, new_status: IssueStatus) -> None:
        """Atualiza status mantendo contadores incrementais. Deve ser chamado dentro do lock."""
        old = self._status.get(issue_id)
        if old == new_status:
            return
        if old is not None and old in self._counts:
            self._counts[old] -= 1
        self._status[issue_id] = new_status
        if new_status in self._counts:
            self._counts[new_status] += 1

    def add_issues(
        self,
        issues: list[Issue],
        priority_issue_types: list[str] | None = None,
    ) -> None:
        """Adiciona issues e ordena por prioridade.

        Se priority_issue_types fornecido, esses tipos vêm primeiro.
        Dentro de cada grupo, ordena por severity (high → medium → low).
        Status inicial: 'queued'.
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

    def mark_processing(self, issue_id: str) -> None:
        """Marca issue como em processamento pelo LLM."""
        with self._lock:
            self._set_status(issue_id, "processing")
        logger.debug("IssueStore: issue {} marcada como processing", issue_id)

    def mark_ready(self, issue_id: str, suggestion_set: SuggestionSet) -> None:
        """Marca issue como pronta (sugestão do LLM chegou)."""
        with self._lock:
            self._suggestions[issue_id] = suggestion_set
            self._set_status(issue_id, "ready")
        logger.debug("IssueStore: issue {} marcada como ready", issue_id)

    def mark_failed(self, issue_id: str, error: str) -> None:
        """Marca issue como falha."""
        with self._lock:
            self._set_status(issue_id, "failed")
            self._suggestions[issue_id] = SuggestionSet(issue_id=issue_id, suggestions=[], error=error)
        logger.warning("IssueStore: issue {} falhou: {}", issue_id, error)

    def get_issue(self, issue_id: str) -> Issue | None:
        """Retorna a Issue pelo id com lock, ou None se não encontrada."""
        with self._lock:
            return self._issues.get(issue_id)

    def get_next_queued(self) -> str | None:
        """Retorna o próximo issue_id com status 'queued', respeitando prioridade."""
        with self._lock:
            while self._queue:
                issue_id = self._queue.popleft()
                if self._status.get(issue_id) == "queued":
                    return issue_id
        return None

    def get_ready_issues(self) -> list[tuple[Issue, SuggestionSet]]:
        """Retorna todas issues prontas."""
        with self._lock:
            result = []
            for issue_id in self._order:
                if self._status.get(issue_id) == "ready":
                    issue = self._issues[issue_id]
                    sset = self._suggestions[issue_id]
                    if sset is not None:
                        result.append((issue, sset))
            return result

    def get_all_with_status(self) -> list[dict]:
        """Retorna lista de {issue, suggestion, status} para a UI."""
        with self._lock:
            return [
                {
                    "issue": self._issues[issue_id],
                    "suggestion": self._suggestions.get(issue_id),
                    "status": self._status.get(issue_id, "queued"),
                }
                for issue_id in self._order
            ]

    def get_progress(self) -> dict:
        """Retorna contagens por status e percent_complete.

        Campos: total, queued, processing, ready, failed, percent_complete.
        percent_complete = (ready + failed) / total * 100
        """
        with self._lock:
            counts = dict(self._counts)
            total = len(self._order)
            done = counts["ready"] + counts["failed"]
            percent = (done / total * 100) if total > 0 else 0.0

            return {
                "total": total,
                **counts,
                "percent_complete": round(percent, 1),
            }

    def requeue(self, issue_id: str) -> None:
        """Recoloca issue na fila após falha, limpando o erro anterior."""
        with self._lock:
            self._set_status(issue_id, "queued")
            self._suggestions[issue_id] = None
            self._queue.appendleft(issue_id)
        logger.debug("IssueStore: issue {} recolocada na fila", issue_id)

    def is_all_done(self) -> bool:
        """Retorna True se nenhum issue está queued ou processing."""
        with self._lock:
            return all(
                s not in ("queued", "processing")
                for s in self._status.values()
            )
