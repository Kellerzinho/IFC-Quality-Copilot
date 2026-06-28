"""Testes do mapeamento de decisão do revisor simulado (F6) e telemetria F12."""

from __future__ import annotations

from src.experiment.evaluator import Evaluator, GroundTruthItem
from src.experiment.reviewer import _decide
from src.models import Issue, Suggestion, SuggestionMetrics, SuggestionSet
from src.suggestion_engine.prompt_templates import parse_llm_response


def _issue(issue_type: str = "space_unnamed") -> Issue:
    return Issue(
        element_guid="G" * 22,
        element_class="IfcSpace",
        issue_type=issue_type,  # type: ignore[arg-type]
        severity="low",
        description="d",
    )


def _sset(issue: Issue, *values, review_required: bool = False) -> SuggestionSet:
    return SuggestionSet(
        issue_id=issue.id,
        suggestions=[
            Suggestion(
                label=str(v),
                value=v,
                justification="j",
                confidence="alta",
                source="llm",
                review_required=review_required,
            )
            for v in values
        ],
    )


def _item(expected="Lavabo", alts=None) -> GroundTruthItem:
    return GroundTruthItem(
        element_guid="G" * 22,
        issue_type="space_unnamed",
        expected_value=expected,
        accepted_alternatives=alts or [],
    )


class TestDecisaoRevisor:
    def test_top1_casa_e_accepted(self):
        issue = _issue()
        decision, value = _decide(issue, _sset(issue, "Lavabo", "Outro"), _item(), Evaluator())
        assert decision == "accepted"
        assert value == "Lavabo"

    def test_top3_casa_e_edited(self):
        issue = _issue()
        sset = _sset(issue, "Errado", "Lavabo", "Outro")
        decision, value = _decide(issue, sset, _item(), Evaluator())
        assert decision == "edited"
        assert value == "Lavabo"

    def test_nada_casa_e_rejected(self):
        issue = _issue()
        decision, value = _decide(issue, _sset(issue, "Errado"), _item(), Evaluator())
        assert decision == "rejected"
        assert value is None

    def test_abstencao_vira_review(self):
        issue = _issue()
        sset = _sset(issue, "Errado", review_required=True)
        decision, _ = _decide(issue, sset, _item(), Evaluator())
        assert decision == "review"

    def test_sem_sugestao_vira_review(self):
        issue = _issue()
        decision, _ = _decide(issue, _sset(issue), _item(), Evaluator())
        assert decision == "review"


class TestTelemetriaReparoJSON:
    def test_json_truncado_marca_json_repaired(self):
        """JSON truncado pelo limite de tokens deve ser reparado e sinalizado."""
        truncated = '{"opcoes": [{"suggested_value": "Sala", "label": "Sala", "justification": "x", "confidence": "alta"'
        telemetry: dict = {}
        suggestions = parse_llm_response(truncated, "space_unnamed", telemetry=telemetry)
        assert telemetry.get("json_found") is True
        assert telemetry.get("json_repaired") is True
        assert len(suggestions) == 1

    def test_json_valido_nao_marca_reparo(self):
        valid = '{"opcoes": [{"suggested_value": "Sala", "label": "Sala", "justification": "x", "confidence": "alta"}]}'
        telemetry: dict = {}
        parse_llm_response(valid, "space_unnamed", telemetry=telemetry)
        assert telemetry.get("json_found") is True
        assert not telemetry.get("json_repaired")

    def test_sem_json_marca_json_not_found(self):
        telemetry: dict = {}
        parse_llm_response("desculpe, não consigo", "space_unnamed", telemetry=telemetry)
        assert telemetry.get("json_found") is False
