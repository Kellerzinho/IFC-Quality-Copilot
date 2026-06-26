"""Testes para os novos estados do IssueStore."""

from __future__ import annotations

from src.models import Issue, Suggestion, SuggestionSet
from src.suggestion_engine.issue_store import IssueStore


def _issue(idx: int = 0, severity: str = "high") -> Issue:
    return Issue(
        element_guid=f"{idx:0>22}"[:22] or "X" * 22,
        element_class="IfcWall",
        element_name=f"Wall {idx}",
        issue_type="pset_missing",
        severity=severity,
        description="x",
        context={},
    )


def _sset(issue_id: str) -> SuggestionSet:
    return SuggestionSet(
        issue_id=issue_id,
        suggestions=[
            Suggestion(
                label="A",
                value="A",
                justification="t",
                confidence="alta",
                source="llm",
            )
        ],
    )


def test_initial_status_is_queued():
    store = IssueStore()
    issue = _issue(1)
    store.add_issues([issue])
    assert store.get_status(issue.id) == "queued"


def test_state_transitions_queued_processing_ready():
    store = IssueStore()
    issue = _issue(1)
    store.add_issues([issue])
    store.mark_processing(issue.id)
    assert store.get_status(issue.id) == "processing"
    store.mark_ready(issue.id, _sset(issue.id))
    assert store.get_status(issue.id) == "ready"


def test_mark_cached_status():
    store = IssueStore()
    issue = _issue(1)
    store.add_issues([issue])
    store.mark_cached(issue.id, _sset(issue.id))
    assert store.get_status(issue.id) == "cached"
    progress = store.get_progress()
    assert progress["cached"] == 1
    assert progress["percent_complete"] == 100.0


def test_mark_reused_records_origin():
    store = IssueStore()
    a, b = _issue(1), _issue(2)
    store.add_issues([a, b])
    store.mark_reused(b.id, _sset(b.id), from_issue_id=a.id)
    items = store.get_all_with_status()
    by_id = {it["issue"].id: it for it in items}
    assert by_id[b.id]["status"] == "reused"
    assert by_id[b.id]["reused_from"] == a.id


def test_mark_review_required():
    store = IssueStore()
    issue = _issue(1)
    store.add_issues([issue])
    store.mark_review_required(issue.id, _sset(issue.id))
    assert store.get_status(issue.id) == "review_required"


def test_backpressure_can_accept_processing():
    store = IssueStore(max_concurrent=1)
    a, b = _issue(1), _issue(2)
    store.add_issues([a, b])
    assert store.can_accept_processing() is True
    store.mark_processing(a.id)
    assert store.can_accept_processing() is False
    store.mark_ready(a.id, _sset(a.id))
    assert store.can_accept_processing() is True


def test_is_all_done_with_terminal_statuses():
    store = IssueStore()
    a, b, c, d = _issue(1), _issue(2), _issue(3), _issue(4)
    store.add_issues([a, b, c, d])
    store.mark_ready(a.id, _sset(a.id))
    store.mark_cached(b.id, _sset(b.id))
    store.mark_reused(c.id, _sset(c.id), from_issue_id=a.id)
    store.mark_failed(d.id, "boom")
    assert store.is_all_done() is True


def test_requeue_clears_origin_and_status():
    store = IssueStore()
    a, b = _issue(1), _issue(2)
    store.add_issues([a, b])
    store.mark_reused(b.id, _sset(b.id), from_issue_id=a.id)
    store.requeue(b.id)
    assert store.get_status(b.id) == "queued"
    items = {it["issue"].id: it for it in store.get_all_with_status()}
    assert items[b.id]["reused_from"] is None
