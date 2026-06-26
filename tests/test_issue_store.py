"""Testes para src/suggestion_engine/issue_store.py."""

import threading
from uuid import uuid4

import pytest

from src.models import Issue, Suggestion, SuggestionSet
from src.suggestion_engine.issue_store import IssueStore

GUID = "3nJOFsJsX8QO2odKZbQnBj"  # 22 chars


def make_issue(severity: str = "medium", issue_type: str = "pset_missing", uid: str | None = None) -> Issue:
    issue = Issue(
        element_guid=GUID,
        element_class="IfcWall",
        issue_type=issue_type,
        severity=severity,
        description="Teste",
    )
    # Ids deterministicos colidem para issues de mesmo conteudo. Nestes testes de
    # store cada issue representa um item distinto, entao forcamos um id unico.
    object.__setattr__(issue, "id", uid or str(uuid4())[:8])
    return issue


def make_suggestion_set(issue_id: str) -> SuggestionSet:
    return SuggestionSet(
        issue_id=issue_id,
        suggestions=[
            Suggestion(
                label="Valor X",
                value="X",
                justification="Justificativa",
                confidence="alta",
                source="llm",
            )
        ],
    )


class TestAddIssues:
    def test_add_issues_sets_queued(self):
        """add_issues deve definir status 'queued' para todos os issues adicionados."""
        store = IssueStore()
        issues = [make_issue(), make_issue()]
        store.add_issues(issues)

        progress = store.get_progress()
        assert progress["total"] == 2
        assert progress["queued"] == 2

    def test_add_issues_priority_ordering(self):
        """Issues de tipos prioritários devem aparecer antes dos demais."""
        store = IssueStore()
        i_low = make_issue(severity="low", issue_type="pset_missing")
        i_space = make_issue(severity="low", issue_type="space_unnamed")

        store.add_issues([i_low, i_space], priority_issue_types=["space_unnamed"])

        first_id = store.get_next_queued()
        assert first_id == i_space.id


class TestStatusTransitions:
    def test_mark_processing_and_ready(self):
        """mark_processing deve mudar status para 'processing'; mark_ready para 'ready'."""
        store = IssueStore()
        issue = make_issue()
        store.add_issues([issue])

        store.mark_processing(issue.id)
        progress = store.get_progress()
        assert progress["processing"] == 1
        assert progress["queued"] == 0

        sset = make_suggestion_set(issue.id)
        store.mark_ready(issue.id, sset)
        progress = store.get_progress()
        assert progress["ready"] == 1
        assert progress["processing"] == 0

        ready = store.get_ready_issues()
        assert len(ready) == 1
        assert ready[0][1].issue_id == issue.id


class TestProgressAndQuery:
    def test_get_next_queued_respects_order(self):
        """get_next_queued deve retornar primeiro da fila (respeitando prioridade definida em add_issues)."""
        store = IssueStore()
        i1 = make_issue(severity="low", issue_type="pset_missing")
        i2 = make_issue(severity="high", issue_type="space_unnamed")
        i3 = make_issue(severity="medium", issue_type="pset_missing")

        # i2 é prioritário pelo tipo; dentro de pset_missing, i3 (medium) vem antes de i1 (low)
        store.add_issues([i1, i2, i3], priority_issue_types=["space_unnamed"])

        first = store.get_next_queued()
        assert first == i2.id

        store.mark_processing(first)
        second = store.get_next_queued()
        assert second == i3.id  # medium severity no grupo normal, antes de i1 (low)

    def test_get_ready_issues(self):
        """get_ready_issues deve retornar issues marcadas como ready."""
        store = IssueStore()
        i1 = make_issue()
        i2 = make_issue()
        store.add_issues([i1, i2])

        store.mark_processing(i1.id)
        store.mark_ready(i1.id, make_suggestion_set(i1.id))
        store.mark_ready(i2.id, make_suggestion_set(i2.id))

        ready = store.get_ready_issues()
        assert len(ready) == 2
        ready_ids = {r[0].id for r in ready}
        assert i1.id in ready_ids
        assert i2.id in ready_ids

    def test_progress_counts(self):
        """get_progress deve contar corretamente cada status e calcular percent_complete."""
        store = IssueStore()
        issues = [make_issue() for _ in range(4)]
        store.add_issues(issues)

        store.mark_processing(issues[0].id)
        store.mark_ready(issues[0].id, make_suggestion_set(issues[0].id))
        store.mark_processing(issues[1].id)
        store.mark_ready(issues[2].id, make_suggestion_set(issues[2].id))
        store.mark_failed(issues[3].id, "erro simulado")

        p = store.get_progress()
        assert p["total"] == 4
        assert p["processing"] == 1
        assert p["ready"] == 2
        assert p["failed"] == 1
        assert p["queued"] == 0
        assert p["percent_complete"] == 75.0  # 3 de 4 terminados (ready + failed)


class TestThreadSafety:
    def test_thread_safety(self):
        """Múltiplas threads fazendo mark_ready simultaneamente não devem corromper o estado."""
        store = IssueStore()
        issues = [make_issue() for _ in range(20)]
        store.add_issues(issues)

        errors: list[Exception] = []

        def worker(issue: Issue) -> None:
            try:
                store.mark_processing(issue.id)
                store.mark_ready(issue.id, make_suggestion_set(issue.id))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(issue,)) for issue in issues]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Erros em threads: {errors}"

        p = store.get_progress()
        assert p["ready"] == 20
        assert p["queued"] == 0
        assert p["processing"] == 0
        assert store.is_all_done() is True
