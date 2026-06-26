"""Testes para SuggestionWorker."""

import time
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.models import Issue, Suggestion, SuggestionSet
from src.suggestion_engine.issue_store import IssueStore
from src.suggestion_engine.suggestion import SuggestionGenerator
from src.suggestion_engine.worker import SuggestionWorker

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BUILDING_CTX = {
    "building_type": "Residencial unifamiliar",
    "bioclimatic_zone": "3",
}


def _make_issue(severity: str = "medium", issue_type: str = "space_unnamed") -> Issue:
    issue = Issue(
        element_guid="G" * 22,
        element_class="IfcSpace",
        element_name="Room 1",
        issue_type=issue_type,
        severity=severity,
        description="Espaço sem nome funcional",
        context={},
    )
    # Cada issue de teste e um item distinto; ids deterministicos colidiriam por
    # terem o mesmo conteudo, entao atribuimos um id unico por fixture.
    object.__setattr__(issue, "id", str(uuid4())[:8])
    return issue


def _make_suggestion_set(issue_id: str) -> SuggestionSet:
    return SuggestionSet(
        issue_id=issue_id,
        suggestions=[
            Suggestion(
                label="Sala de Estar",
                value="Sala de Estar",
                justification="Área compatível",
                confidence="alta",
                source="llm",
            )
        ],
    )


def _make_generator() -> MagicMock:
    return MagicMock(spec=SuggestionGenerator)


def _wait_until(condition, timeout: float = 3.0, interval: float = 0.05) -> bool:
    """Aguarda condição ser True ou timeout expirar. Retorna True se condiu."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(interval)
    return False


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------


def test_worker_processes_queued_issues():
    """Worker deve processar todas as issues na fila e marcá-las como ready."""
    store = IssueStore()
    issue1 = _make_issue(severity="high")
    issue2 = _make_issue(severity="low")
    store.add_issues([issue1, issue2])

    generator = _make_generator()
    generator.generate.side_effect = lambda issue, ctx: _make_suggestion_set(issue.id)

    worker = SuggestionWorker(store, generator, _BUILDING_CTX)
    worker.start()

    try:
        concluiu = _wait_until(store.is_all_done)
        assert concluiu, "Worker não terminou dentro do timeout"

        ready = store.get_ready_issues()
        assert len(ready) == 2
        assert generator.generate.call_count == 2
    finally:
        worker.stop()


def test_worker_stops_when_all_done():
    """Thread do worker deve encerrar naturalmente após processar todas as issues."""
    store = IssueStore()
    issue = _make_issue()
    store.add_issues([issue])

    generator = _make_generator()
    generator.generate.return_value = _make_suggestion_set(issue.id)

    worker = SuggestionWorker(store, generator, _BUILDING_CTX)
    worker.start()

    # Aguarda thread finalizar por conta própria
    worker._thread.join(timeout=3.0)
    assert not worker.is_running, "Thread deveria ter encerrado sozinha"


def test_worker_handles_generation_failure():
    """Worker deve marcar issues como failed quando generator lança exceção."""
    store = IssueStore()
    issue = _make_issue()
    store.add_issues([issue])

    generator = _make_generator()
    generator.generate.side_effect = RuntimeError("Ollama indisponível")

    worker = SuggestionWorker(store, generator, _BUILDING_CTX)
    worker.start()

    try:
        concluiu = _wait_until(store.is_all_done)
        assert concluiu, "Worker não terminou dentro do timeout"

        progress = store.get_progress()
        assert progress["failed"] == 1
        assert progress["ready"] == 0
    finally:
        worker.stop()


def test_worker_stop_signal():
    """stop() deve interromper o worker mesmo que haja issues pendentes."""
    # Store mockado: sem issues queued, mas is_all_done() retorna False
    # → worker fica no loop de sleep esperando por trabalho
    store = MagicMock(spec=IssueStore)
    store.get_next_queued.return_value = None
    store.is_all_done.return_value = False

    generator = _make_generator()
    worker = SuggestionWorker(store, generator, _BUILDING_CTX)
    worker.start()

    assert worker.is_running

    worker.stop()
    assert not worker.is_running, "Thread não parou após stop()"


def test_worker_respects_priority_order():
    """Worker deve processar issues de maior severidade antes das de menor."""
    store = IssueStore()
    issue_low = _make_issue(severity="low")
    issue_high = _make_issue(severity="high")
    issue_medium = _make_issue(severity="medium")

    # Adicionadas em ordem inversa à prioridade
    store.add_issues([issue_low, issue_high, issue_medium])

    processed_order: list[str] = []

    def capture_order(issue, ctx):
        processed_order.append(issue.id)
        return _make_suggestion_set(issue.id)

    generator = _make_generator()
    generator.generate.side_effect = capture_order

    worker = SuggestionWorker(store, generator, _BUILDING_CTX)
    worker.start()

    try:
        concluiu = _wait_until(store.is_all_done)
        assert concluiu, "Worker não terminou dentro do timeout"

        assert len(processed_order) == 3
        # high deve ser o primeiro processado
        assert processed_order[0] == issue_high.id, (
            f"Esperado high ({issue_high.id}) primeiro, obtido {processed_order[0]}"
        )
        # low deve ser o último
        assert processed_order[-1] == issue_low.id, (
            f"Esperado low ({issue_low.id}) último, obtido {processed_order[-1]}"
        )
    finally:
        worker.stop()
