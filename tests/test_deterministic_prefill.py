"""Testes do pré-preenchimento determinístico (Fase A.3).

Garante que casos triviais (lista fechada) geram sugestão sem chamar o LLM,
com source="deterministic", e que os demais casos seguem o fluxo normal.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.models import Issue
from src.suggestion_engine.deterministic import generate_deterministic_suggestions
from src.suggestion_engine.ollama_client import OllamaClient
from src.suggestion_engine.suggestion import SuggestionGenerator

_BUILDING_CTX = {
    "building_type": "Residencial unifamiliar",
    "bioclimatic_zone": "3",
}

_VALID_LLM_RESPONSE = (
    '{"opcoes": [{"suggested_value": "X", "label": "X", '
    '"justification": "Mock.", "confidence": "media"}]}'
)


def _make_client() -> MagicMock:
    client = MagicMock(spec=OllamaClient)
    client.generate.return_value = _VALID_LLM_RESPONSE
    return client


def _pset_issue(
    check_property: str,
    element_class: str = "IfcWall",
    extra_context: dict | None = None,
) -> Issue:
    context = {"check_pset": "Pset_WallCommon", "check_property": check_property}
    context.update(extra_context or {})
    return Issue(
        element_guid="E" * 22,
        element_class=element_class,
        element_name="Elemento 01",
        issue_type="pset_missing",
        severity="medium",
        description=f"{check_property} ausente",
        context=context,
    )


# ---------------------------------------------------------------------------
# Função pura: generate_deterministic_suggestions
# ---------------------------------------------------------------------------


class TestIsExternalPrefill:
    @pytest.mark.parametrize("derived", [True, False])
    def test_is_external_derived_from_boundary_analysis(self, derived: bool):
        issue = _pset_issue("IsExternal", extra_context={"is_external": derived})
        suggestions = generate_deterministic_suggestions(issue)

        assert len(suggestions) == 1
        assert suggestions[0].value is derived
        assert suggestions[0].source == "deterministic"
        assert suggestions[0].confidence == "alta"

    def test_is_external_falls_back_to_is_on_exterior(self):
        issue = _pset_issue("IsExternal", extra_context={"is_on_exterior": True})
        suggestions = generate_deterministic_suggestions(issue)

        assert len(suggestions) == 1
        assert suggestions[0].value is True

    def test_is_external_string_form_is_coerced(self):
        issue = _pset_issue("IsExternal", extra_context={"is_external": "true"})
        suggestions = generate_deterministic_suggestions(issue)

        assert len(suggestions) == 1
        assert suggestions[0].value is True

    def test_is_external_without_boundary_info_yields_nothing(self):
        """Sem análise de fronteira não há derivação — abstém-se do prefill."""
        issue = _pset_issue("IsExternal")
        assert generate_deterministic_suggestions(issue) == []

    def test_is_external_ambiguous_value_yields_nothing(self):
        issue = _pset_issue("IsExternal", extra_context={"is_external": "talvez"})
        assert generate_deterministic_suggestions(issue) == []


class TestLoadBearingPrefill:
    @pytest.mark.parametrize(
        "element_class", ["IfcBeam", "IfcColumn", "IfcBeamStandardCase", "IfcColumnStandardCase"]
    )
    def test_load_bearing_true_for_structural_classes(self, element_class: str):
        issue = _pset_issue("LoadBearing", element_class=element_class)
        suggestions = generate_deterministic_suggestions(issue)

        assert len(suggestions) == 1
        assert suggestions[0].value is True
        assert suggestions[0].source == "deterministic"

    def test_is_load_bearing_alias_also_matches(self):
        issue = _pset_issue("IsLoadBearing", element_class="IfcBeam")
        assert len(generate_deterministic_suggestions(issue)) == 1

    def test_load_bearing_on_wall_is_not_prefilled(self):
        """Parede pode ou não ser portante — caso ambíguo vai para o LLM."""
        issue = _pset_issue("LoadBearing", element_class="IfcWall")
        assert generate_deterministic_suggestions(issue) == []


class TestClosedList:
    def test_property_outside_closed_list_yields_nothing(self):
        issue = _pset_issue("FireRating", extra_context={"is_external": True})
        assert generate_deterministic_suggestions(issue) == []

    def test_non_pset_issue_yields_nothing(self):
        issue = Issue(
            element_guid="S" * 22,
            element_class="IfcSpace",
            issue_type="space_unnamed",
            severity="low",
            description="Espaço sem nome",
            context={"is_external": True},
        )
        assert generate_deterministic_suggestions(issue) == []


# ---------------------------------------------------------------------------
# Integração: SuggestionGenerator não chama Ollama no caminho determinístico
# ---------------------------------------------------------------------------


class TestGeneratorIntegration:
    def test_deterministic_path_does_not_call_ollama(self):
        client = _make_client()
        gen = SuggestionGenerator(client)
        issue = _pset_issue("IsExternal", extra_context={"is_on_exterior": True})

        result = gen.generate(issue, _BUILDING_CTX)

        client.generate.assert_not_called()
        assert result.has_suggestions
        assert result.suggestions[0].source == "deterministic"
        assert result.metrics is not None
        assert result.metrics.final_status == "deterministic"
        assert result.metrics.attempts == 0

    def test_non_trivial_case_still_calls_ollama(self):
        client = _make_client()
        gen = SuggestionGenerator(client)
        issue = _pset_issue("IsExternal")  # sem análise de fronteira

        result = gen.generate(issue, _BUILDING_CTX)

        client.generate.assert_called()
        assert result.suggestions[0].source == "llm"
