"""Testes de validação de sugestões contra vocabulário bSDD."""

from unittest.mock import MagicMock

from src.models import BSDDClassification, BSDDContext, BSDDProperty, Issue
from src.suggestion_engine.ollama_client import OllamaClient
from src.suggestion_engine.suggestion import SuggestionGenerator


_BUILDING_CTX = {
    "building_type": "Residencial unifamiliar",
    "bioclimatic_zone": "3",
}


def _make_client(response: str) -> MagicMock:
    client = MagicMock(spec=OllamaClient)
    client.generate.return_value = response
    return client


def _make_pset_issue(check_property: str = "FireRating") -> Issue:
    return Issue(
        element_guid="W" * 22,
        element_class="IfcWall",
        element_name="Parede 01",
        issue_type="pset_missing",
        severity="high",
        description=f"{check_property} ausente",
        context={"check_property": check_property},
    )


def _make_space_issue() -> Issue:
    return Issue(
        element_guid="S" * 22,
        element_class="IfcSpace",
        element_name="Room 01",
        issue_type="space_unnamed",
        severity="low",
        description="Espaço sem nome funcional",
        context={},
    )


def test_suggestion_within_vocabulary_keeps_confidence():
    client = _make_client(
        '{"opcoes": [{"value": 2.48, "justification": "Valor previsto.", "confidence": "alta"}]}'
    )
    gen = SuggestionGenerator(client)
    issue = _make_pset_issue("ThermalTransmittance")
    bsdd_context = BSDDContext(
        issue_id=issue.id,
        element_class="IfcWall",
        search_query="Wall",
        properties=[
            BSDDProperty(
                name="ThermalTransmittance",
                data_type="real",
                unit="W/(m².K)",
                allowed_values=["2.48", "3.00"],
            )
        ],
    )

    result = gen.generate(issue, _BUILDING_CTX, bsdd_context=bsdd_context)

    assert result.suggestions[0].confidence == "alta"
    assert "fora do vocabulário bSDD" not in result.suggestions[0].justification


def test_suggestion_outside_vocabulary_gets_downgraded():
    client = _make_client(
        '{"opcoes": [{"label": "Quarto", "value": "Quarto", "justification": "Adjacente ao corredor.", "confidence": "alta"}]}'
    )
    gen = SuggestionGenerator(client)
    issue = _make_space_issue()
    bsdd_context = BSDDContext(
        issue_id=issue.id,
        element_class="IfcSpace",
        search_query="Space",
        classes=[BSDDClassification(name="Sala"), BSDDClassification(name="Banheiro")],
    )

    result = gen.generate(issue, _BUILDING_CTX, bsdd_context=bsdd_context)

    assert result.suggestions[0].confidence == "baixa"
    assert "fora do vocabulário bSDD" in result.suggestions[0].justification


def test_numeric_type_mismatch_gets_downgraded():
    client = _make_client(
        '{"opcoes": [{"value": "abc", "justification": "Estimativa textual.", "confidence": "media"}]}'
    )
    gen = SuggestionGenerator(client)
    issue = _make_pset_issue("ThermalTransmittance")
    bsdd_context = BSDDContext(
        issue_id=issue.id,
        element_class="IfcWall",
        search_query="Wall",
        properties=[BSDDProperty(name="ThermalTransmittance", data_type="real")],
    )

    result = gen.generate(issue, _BUILDING_CTX, bsdd_context=bsdd_context)

    assert result.suggestions == []
    assert result.error is not None


def test_no_bsdd_context_skips_validation():
    client = _make_client(
        '{"opcoes": [{"label": "Quarto", "value": "Quarto", "justification": "Adjacente ao corredor.", "confidence": "alta"}]}'
    )
    gen = SuggestionGenerator(client)
    issue = _make_space_issue()

    result = gen.generate(issue, _BUILDING_CTX, bsdd_context=None)

    assert result.suggestions[0].confidence == "alta"
    assert "bSDD" not in result.suggestions[0].justification
