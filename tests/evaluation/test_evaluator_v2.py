"""Testes da Fase 0.3 (F10+F11): comparação normalizada, chave natural e loader YAML."""

from __future__ import annotations

import pytest

from src.experiment.evaluator import (
    Evaluator,
    GroundTruth,
    GroundTruthItem,
    values_match,
)
from src.models import Issue, Suggestion, SuggestionSet


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _issue(
    issue_type: str,
    *,
    element_guid: str = "A" * 22,
    check_property: str = "",
    check_pset: str = "",
    issue_id: str | None = None,
    element_class: str = "IfcWall",
) -> Issue:
    context: dict[str, object] = {}
    if check_property:
        context["check_property"] = check_property
    if check_pset:
        context["check_pset"] = check_pset
    kwargs: dict[str, object] = dict(
        element_guid=element_guid,
        element_class=element_class,
        issue_type=issue_type,
        severity="high",
        description="issue de teste",
        context=context,
    )
    if issue_id is not None:
        kwargs["id"] = issue_id
    return Issue(**kwargs)  # type: ignore[arg-type]


def _pair(issue: Issue, *values: object) -> tuple[Issue, SuggestionSet]:
    suggestions = [
        Suggestion(
            label=str(v),
            value=v,
            justification="just",
            confidence="alta",
            source="llm",
        )
        for v in values
    ]
    return issue, SuggestionSet(issue_id=issue.id, suggestions=suggestions)


# ---------------------------------------------------------------------------
# Comparação normalizada (F10)
# ---------------------------------------------------------------------------


class TestComparacaoNumericaNormalizada:
    """Floats equivalentes em formatos diferentes devem casar (substitui str==str)."""

    @pytest.mark.parametrize("candidate", [2.5, "2,50", "2.50 W/m²K", "2.50 W/(m².K)"])
    def test_thermal_transmittance_formatos_equivalentes(self, candidate):
        """2.5 ≡ "2,50" ≡ "2.50 W/m²K" para ThermalTransmittance."""
        issue = _issue("pset_missing", check_property="ThermalTransmittance")
        assert values_match(issue, candidate, 2.5)

    def test_tolerancia_relativa_aceita_pequena_diferenca(self):
        """2.54 está dentro de 2% de 2.50 → casa."""
        issue = _issue("pset_missing", check_property="ThermalTransmittance")
        assert values_match(issue, 2.54, 2.50)

    def test_tolerancia_relativa_rejeita_diferenca_grande(self):
        """2.60 está fora de 2% de 2.50 → não casa."""
        issue = _issue("pset_missing", check_property="ThermalTransmittance")
        assert not values_match(issue, 2.60, 2.50)


class TestComparacaoBooleanaNormalizada:
    """Booleanos em formatos textuais/numéricos devem casar."""

    @pytest.mark.parametrize("candidate", [True, "true", "True", "sim", "1"])
    def test_true_em_varios_formatos(self, candidate):
        """True ≡ "true" ≡ "sim" ≡ "1" para um booleano de Pset."""
        issue = _issue("pset_missing", check_property="IsExternal")
        assert values_match(issue, candidate, True)

    def test_false_nao_casa_true(self):
        """"false" não deve casar com True."""
        issue = _issue("pset_missing", check_property="IsExternal")
        assert not values_match(issue, "false", True)


class TestComparacaoTextualNormalizada:
    """Strings devem comparar insensível a acento/caixa/espaços."""

    @pytest.mark.parametrize("candidate", ["Banheiro Social", "banheiro social", " BANHEIRO  SOCIAL "])
    def test_espaco_casefold_acentos(self, candidate):
        issue = _issue("space_unnamed", element_class="IfcSpace")
        assert values_match(issue, candidate, "Banheiro Social")


# ---------------------------------------------------------------------------
# Chave natural e accepted_alternatives
# ---------------------------------------------------------------------------


class TestChaveNatural:
    """GT por chave natural casa issues entre execuções, mesmo com id diferente."""

    def test_casa_por_chave_natural_ignorando_id(self):
        """Issue com id arbitrário casa o GT pela chave natural (guid, tipo, propriedade)."""
        gt = GroundTruth(
            items=[
                GroundTruthItem(
                    element_guid="GUID1234567890ABCDEFGH",
                    issue_type="pset_missing",
                    check_property="ThermalTransmittance",
                    expected_value=2.5,
                )
            ]
        )
        issue = _issue(
            "pset_missing",
            element_guid="GUID1234567890ABCDEFGH",
            check_property="ThermalTransmittance",
            issue_id="id-arbitrario-de-outra-execucao",
        )
        item = gt.get_for_issue(issue)
        assert item is not None
        assert item.expected_value == 2.5

    def test_fallback_por_issue_id(self):
        """Sem chave natural, casa por issue_id (compat legada)."""
        gt = GroundTruth(corrections={"i1": "2.48"})
        issue = _issue("pset_missing", issue_id="i1")
        item = gt.get_for_issue(issue)
        assert item is not None
        assert item.expected_value == "2.48"

    def test_chave_natural_diferente_nao_casa(self):
        """GUID diferente não deve casar."""
        gt = GroundTruth(
            items=[
                GroundTruthItem(
                    element_guid="GUID_A",
                    issue_type="pset_missing",
                    check_property="ThermalTransmittance",
                    expected_value=2.5,
                )
            ]
        )
        issue = _issue("pset_missing", element_guid="GUID_B", check_property="ThermalTransmittance")
        assert gt.get_for_issue(issue) is None


class TestAcceptedAlternatives:
    """Itens com accepted_alternatives aceitam múltiplos valores corretos."""

    def test_alternativa_casa_no_evaluator(self):
        gt = GroundTruth(
            items=[
                GroundTruthItem(
                    element_guid="B" * 22,
                    issue_type="space_unnamed",
                    expected_value="Lavabo",
                    accepted_alternatives=["WC Social", "Banheiro Social"],
                )
            ]
        )
        issue = _issue("space_unnamed", element_guid="B" * 22, element_class="IfcSpace")
        results = [_pair(issue, "WC Social")]

        evaluator = Evaluator()
        metrics = evaluator.evaluate(results, gt)
        assert metrics.total_evaluated == 1
        assert metrics.accuracy_top1 == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Loader YAML
# ---------------------------------------------------------------------------


class TestLoaderYAML:
    """GroundTruth.from_yaml carrega e valida um arquivo versionável."""

    def test_carrega_yaml_e_casa_issues(self, tmp_path):
        yaml_text = """
metadata:
  source: predio_v1
  verified_by: Felipe
  date: 2026-06-28
items:
  - element_guid: GUID_PAREDE_01
    issue_type: pset_missing
    check_property: ThermalTransmittance
    expected_value: 2.5
    verified: true
  - element_guid: GUID_ESPACO_01
    issue_type: space_unnamed
    expected_value: Lavabo
    accepted_alternatives:
      - WC Social
    verified: true
"""
        path = tmp_path / "ground_truth.yaml"
        path.write_text(yaml_text, encoding="utf-8")

        gt = GroundTruth.from_yaml(path)
        assert len(gt.items) == 2
        assert gt.metadata["verified_by"] == "Felipe"

        wall = _issue(
            "pset_missing",
            element_guid="GUID_PAREDE_01",
            check_property="ThermalTransmittance",
        )
        space = _issue("space_unnamed", element_guid="GUID_ESPACO_01", element_class="IfcSpace")

        assert values_match(wall, "2,50", gt.get_for_issue(wall).expected_value)
        space_item = gt.get_for_issue(space)
        assert "WC Social" in space_item.accepted_alternatives


# ---------------------------------------------------------------------------
# Métricas (F11) — precision condicionada à geração
# ---------------------------------------------------------------------------


class TestMetricasFormalizadas:
    """precision = acertos top-1 / issues com sugestão; recall sobre todo o GT."""

    def test_precision_ignora_abstencao_recall_nao(self):
        """Issue sem sugestão entra no recall (como erro) mas não na precision."""
        gt = GroundTruth(
            items=[
                GroundTruthItem(element_guid="W1" + "x" * 20, issue_type="pset_missing",
                                check_property="ThermalTransmittance", expected_value=2.5),
                GroundTruthItem(element_guid="W2" + "x" * 20, issue_type="pset_missing",
                                check_property="ThermalTransmittance", expected_value=2.5),
            ]
        )
        i_hit = _issue("pset_missing", element_guid="W1" + "x" * 20, check_property="ThermalTransmittance")
        i_abstain = _issue("pset_missing", element_guid="W2" + "x" * 20, check_property="ThermalTransmittance")
        results = [_pair(i_hit, 2.5), _pair(i_abstain)]  # segunda sem sugestão

        metrics = Evaluator().evaluate(results, gt)
        # 1 acerto entre 1 issue com sugestão → precision 1.0
        assert metrics.precision == pytest.approx(1.0)
        # 1 acerto entre 2 itens de GT → recall 0.5
        assert metrics.recall == pytest.approx(0.5)
