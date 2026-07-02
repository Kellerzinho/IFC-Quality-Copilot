"""Testes do template pset_missing_generic_grounded e roteamento (Fase A.1/A.2)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.models import BSDDContext, BSDDProperty, IDSContext, Issue
from src.suggestion_engine.grounding import prepare_llm_grounding
from src.suggestion_engine.ollama_client import OllamaClient
from src.suggestion_engine.prompt_templates import (
    PROMPT_VERSION,
    build_pset_grounded_prompt,
    has_specialized_pset_template,
)
from src.suggestion_engine.suggestion import SuggestionGenerator

_BUILDING_CTX = {
    "building_type": "Residencial unifamiliar",
    "bioclimatic_zone": "3",
}


def _make_client(response: str) -> MagicMock:
    client = MagicMock(spec=OllamaClient)
    client.generate.return_value = response
    return client


def _rich_pset_issue(check_property: str = "Reference") -> Issue:
    """Issue pset_missing genérica com contexto rico do elemento."""
    return Issue(
        element_guid="W" * 22,
        element_class="IfcWall",
        element_name="Parede externa 01",
        issue_type="pset_missing",
        severity="medium",
        description=f"{check_property} ausente",
        context={
            "check_pset": "Pset_WallCommon",
            "check_property": check_property,
            "materials": [
                {"name": "Bloco cerâmico", "thickness_m": 0.14},
                {"name": "Reboco", "thickness_m": 0.025},
            ],
            "thickness_m": 0.19,
            "predefined_type": "SOLIDWALL",
            "is_external": True,
            "floor": "Pavimento Térreo",
            "existing_psets": ["Pset_WallCommon"],
        },
    )


def _ids_context(check_property: str = "Reference") -> IDSContext:
    return IDSContext(
        spec_name="NBR15575",
        requirement_description=f"Pset_WallCommon.{check_property} must exist",
        check_type="exists",
        expected_pset="Pset_WallCommon",
        expected_property=check_property,
        expected_value=None,
        expected_unit=None,
        severity="medium",
        requirement_id="rule-ref-1",
    )


def _bsdd_with_allowed_values(check_property: str = "Reference") -> BSDDContext:
    return BSDDContext(
        class_name="Wall",
        related_properties=[
            BSDDProperty(
                name=check_property,
                data_type="String",
                allowed_values=["ALV-VED-CER", "ALV-EST-CER", "CONC-MOLD"],
            )
        ],
        source_status="live",
    )


def _bsdd_typed_only(check_property: str = "Reference") -> BSDDContext:
    return BSDDContext(
        class_name="Wall",
        related_properties=[
            BSDDProperty(name=check_property, data_type="String", unit=None)
        ],
        source_status="live",
    )


# ---------------------------------------------------------------------------
# A.1 — GroundedIssueContext enriquecido
# ---------------------------------------------------------------------------


class TestGroundedContextElementFields:
    def test_grounded_context_includes_element_rich_fields(self):
        """material_layers, thickness_m, predefined_type, is_external e floor
        devem ser extraídos do contexto da issue."""
        g = prepare_llm_grounding(_rich_pset_issue(), ids_context=_ids_context())

        assert len(g.material_layers) == 2
        assert g.material_layers[0]["name"] == "Bloco cerâmico"
        assert g.thickness_m == pytest.approx(0.19)
        assert g.predefined_type == "SOLIDWALL"
        assert g.is_external is True
        assert g.floor == "Pavimento Térreo"
        assert g.existing_psets == ["Pset_WallCommon"]

    def test_grounded_context_coerces_string_forms(self):
        """Valores em formato string (vindos de serialização) são coagidos."""
        issue = _rich_pset_issue()
        issue.context["thickness_m"] = "0,19"
        issue.context["is_external"] = "true"
        g = prepare_llm_grounding(issue, ids_context=_ids_context())

        assert g.thickness_m == pytest.approx(0.19)
        assert g.is_external is True

    def test_grounded_context_missing_fields_default_to_none(self):
        """Issue sem contexto rico não inventa valores."""
        issue = Issue(
            element_guid="W" * 22,
            element_class="IfcWall",
            issue_type="pset_missing",
            severity="medium",
            description="Reference ausente",
            context={"check_pset": "Pset_WallCommon", "check_property": "Reference"},
        )
        g = prepare_llm_grounding(issue, ids_context=_ids_context())

        assert g.material_layers == []
        assert g.thickness_m is None
        assert g.predefined_type is None
        assert g.is_external is None
        assert g.floor is None

    def test_grounded_context_falls_back_to_is_on_exterior(self):
        """is_on_exterior (análise de fronteira) alimenta is_external quando ausente."""
        issue = _rich_pset_issue()
        del issue.context["is_external"]
        issue.context["is_on_exterior"] = False
        g = prepare_llm_grounding(issue, ids_context=_ids_context())

        assert g.is_external is False


# ---------------------------------------------------------------------------
# A.1 — Template grounded: 3 cenários de bSDD
# ---------------------------------------------------------------------------


class TestPsetGroundedPromptScenarios:
    def test_scenario_closed_vocabulary(self):
        """bSDD com allowed_values → vocabulário fechado no prompt."""
        g = prepare_llm_grounding(
            _rich_pset_issue(),
            ids_context=_ids_context(),
            bsdd_context=_bsdd_with_allowed_values(),
        )
        _, user = build_pset_grounded_prompt(g)

        assert "VALORES PERMITIDOS" in user
        assert "ALV-VED-CER" in user
        assert "APENAS" in user

    def test_scenario_typed_value_only(self):
        """bSDD só com data_type → valor tipado + review_required condicional."""
        g = prepare_llm_grounding(
            _rich_pset_issue(),
            ids_context=_ids_context(),
            bsdd_context=_bsdd_typed_only(),
        )
        _, user = build_pset_grounded_prompt(g)

        assert "VALORES PERMITIDOS" not in user
        assert "TIPADO" in user
        assert "review_required=true" in user

    def test_scenario_bsdd_empty_abstains(self):
        """Sem bSDD e sem tipo → abstenção por padrão."""
        issue = _rich_pset_issue()
        ids = _ids_context()
        g = prepare_llm_grounding(issue, ids_context=ids, bsdd_context=None)
        _, user = build_pset_grounded_prompt(g)

        assert "VALORES PERMITIDOS" not in user
        assert "abster" in user
        assert "review_required=true por padrao" in user

    def test_prompt_includes_element_rich_context(self):
        """Contexto rico do elemento entra no prompt grounded."""
        g = prepare_llm_grounding(
            _rich_pset_issue(),
            ids_context=_ids_context(),
            bsdd_context=_bsdd_with_allowed_values(),
        )
        _, user = build_pset_grounded_prompt(g)

        assert "camadas_material" in user
        assert "Bloco cerâmico" in user
        assert "espessura_total_m: 0.19" in user
        assert "predefined_type: SOLIDWALL" in user
        assert "is_external: True" in user
        assert "pavimento: Pavimento Térreo" in user
        assert "REQUISITO IDS:" in user

    def test_prompt_keeps_compact_output_contract(self):
        """O contrato de saída compacto (JSON com review_required) é mantido."""
        g = prepare_llm_grounding(_rich_pset_issue(), ids_context=_ids_context())
        _, user = build_pset_grounded_prompt(g)

        assert '"opcoes"' in user
        assert "review_required" in user
        assert "Maximo 3 opcoes" in user


# ---------------------------------------------------------------------------
# A.1 — PROMPT_VERSION v3 com fonte única
# ---------------------------------------------------------------------------


class TestPromptVersion:
    def test_prompt_version_is_v3(self):
        assert PROMPT_VERSION == "v3"

    def test_prompt_version_single_source(self):
        """suggestion_cache re-exporta a mesma constante (sem deriva)."""
        from src.suggestion_engine.suggestion_cache import (
            PROMPT_VERSION as cache_version,
        )

        assert cache_version == PROMPT_VERSION


# ---------------------------------------------------------------------------
# A.2 — Roteamento grounded vs especializado vs fallback
# ---------------------------------------------------------------------------


class TestSpecializedTemplateDetection:
    @pytest.mark.parametrize(
        ("check_property", "expected"),
        [
            ("ThermalTransmittance", True),
            ("FireRating", True),
            ("AcousticRating", True),
            ("SolarHeatGainCoefficient", True),
            ("LoadBearing", True),
            ("Reference", False),
            ("IsExternal", False),
        ],
    )
    def test_has_specialized_pset_template(self, check_property: str, expected: bool):
        issue = _rich_pset_issue(check_property)
        assert has_specialized_pset_template(issue) is expected

    def test_non_pset_issue_is_not_specialized(self):
        issue = Issue(
            element_guid="S" * 22,
            element_class="IfcSpace",
            issue_type="space_unnamed",
            severity="low",
            description="Espaço sem nome",
            context={},
        )
        assert has_specialized_pset_template(issue) is False


class TestGroundedRouting:
    _VALID_RESPONSE = (
        '{"opcoes": [{"suggested_value": "ALV-VED-CER", "label": "ALV-VED-CER", '
        '"justification": "Vocabulario bSDD.", "confidence": "alta"}]}'
    )

    def test_generic_pset_with_grounding_uses_grounded_template(self):
        """pset_missing genérico COM grounding → prompt grounded dedicado."""
        client = _make_client(self._VALID_RESPONSE)
        gen = SuggestionGenerator(client)
        issue = _rich_pset_issue("Reference")

        gen.generate(
            issue,
            _BUILDING_CTX,
            ids_context=_ids_context("Reference"),
            bsdd_context=_bsdd_with_allowed_values("Reference"),
        )

        prompt = client.generate.call_args.kwargs["prompt"]
        assert "REQUISITO IDS:" in prompt
        assert "VALORES PERMITIDOS" in prompt

    def test_specialized_pset_with_grounding_keeps_compact_path(self):
        """pset_missing especializado (FireRating) segue no prompt compacto."""
        client = _make_client(
            '{"opcoes": [{"suggested_value": "REI 60", "label": "REI 60", '
            '"justification": "Usual em vedacao.", "confidence": "alta"}]}'
        )
        gen = SuggestionGenerator(client)
        issue = _rich_pset_issue("FireRating")

        gen.generate(issue, _BUILDING_CTX, ids_context=_ids_context("FireRating"))

        prompt = client.generate.call_args.kwargs["prompt"]
        assert "REQUISITO IDS:" not in prompt
        assert "issue_id" in prompt  # caminho compacto

    def test_generic_pset_without_grounding_uses_hardened_fallback(self):
        """SEM grounding → template genérico endurecido com abstenção."""
        client = _make_client(self._VALID_RESPONSE)
        gen = SuggestionGenerator(client)
        issue = _rich_pset_issue("Reference")

        gen.generate(issue, _BUILDING_CTX)

        prompt = client.generate.call_args.kwargs["prompt"]
        assert "ABSTENÇÃO" in prompt
        assert "review_required" in prompt
