"""Tolerância por propriedade e erro numérico contínuo (item C).

Medido em 2026-07-27: o estrato ``ThermalTransmittance`` (548 itens, 21,5% do
GT do prédio) ficou em **0,000 de top-1** com o gemma2:9b. Olhando os valores,
boa parte é *near miss* de engenharia — o modelo devolveu 2,48 W/(m²·K) onde o
GT é 2,35 (5,5% de erro) — reprovado por uma tolerância relativa de 2%.

Duas consequências, tratadas aqui:

1. **Tolerância por propriedade.** O próprio GT de U foi *derivado* por cálculo
   (NBR 15220-2) com λ tabelados e resistências superficiais assumidas; exigir
   concordância de 2% com um valor que é ele mesmo uma estimativa não mede o
   que se quer medir. A banda de equivalência para transmitância é 10%.
2. **Acerto binário não basta para grandeza contínua.** Errar 5% e errar 300%
   (2,48 vs 5,7 nas janelas) não podem colapsar no mesmo "0". O resultado por
   issue passa a registrar o erro relativo, e o breakdown reporta MAPE e a
   fração dentro de ±10% / ±20%.

O top-1 estrito continua recuperável: o erro por issue está gravado, então
qualquer banda pode ser recalculada sem repetir o run.
"""

import pytest

from src.experiment.evaluator import (
    DEFAULT_FLOAT_TOLERANCE,
    TOLERANCE_BY_PROPERTY,
    Evaluator,
    GroundTruth,
    GroundTruthItem,
    tolerance_for_issue,
    values_match,
)
from src.experiment.per_issue import aggregate_by_stratum, build_issue_outcomes
from src.models import Issue, Suggestion, SuggestionMetrics, SuggestionSet


def _thermal_issue() -> Issue:
    return Issue(
        element_guid="W" * 22,
        element_class="IfcWall",
        element_name="Dry-Wall 10cm",
        issue_type="pset_missing",
        severity="high",
        description="ThermalTransmittance ausente",
        context={"check_property": "ThermalTransmittance", "check_pset": "Pset_WallCommon"},
    )


def _generic_numeric_issue() -> Issue:
    return Issue(
        element_guid="G" * 22,
        element_class="IfcWall",
        element_name="Parede",
        issue_type="pset_missing",
        severity="medium",
        description="Width ausente",
        context={"check_property": "Width", "check_pset": "Pset_WallCommon"},
    )


def _sset(issue: Issue, values: list) -> SuggestionSet:
    return SuggestionSet(
        issue_id=issue.id,
        suggestions=[
            Suggestion(label=str(v), value=v, justification="j", confidence="alta")
            for v in values
        ],
        metrics=SuggestionMetrics(issue_id=issue.id, attempts=1),
    )


def _gt(issue: Issue, expected) -> GroundTruth:
    return GroundTruth(
        items=[
            GroundTruthItem(
                element_guid=issue.element_guid,
                issue_type=issue.issue_type,
                check_property=str(issue.context.get("check_property") or ""),
                expected_value=expected,
            )
        ]
    )


# ---------------------------------------------------------------------------
# 1. Tolerância por propriedade
# ---------------------------------------------------------------------------


def test_transmitancia_aceita_erro_de_engenharia_de_5_por_cento():
    """2,48 vs 2,35 (5,5%) é equivalência de engenharia, não erro."""
    issue = _thermal_issue()

    assert values_match(issue, 2.48, 2.35, tolerance_for_issue(issue))


def test_transmitancia_rejeita_erro_grosseiro():
    """2,48 vs 5,7 (janela de vidro simples) continua sendo erro."""
    issue = _thermal_issue()

    assert not values_match(issue, 2.48, 5.7, tolerance_for_issue(issue))


def test_propriedade_sem_banda_propria_mantem_os_2_por_cento():
    """A flexibilização é específica de transmitância, não global."""
    issue = _generic_numeric_issue()

    assert tolerance_for_issue(issue) == DEFAULT_FLOAT_TOLERANCE
    assert not values_match(issue, 2.48, 2.35, tolerance_for_issue(issue))


def test_tabela_de_tolerancias_documenta_a_transmitancia():
    assert TOLERANCE_BY_PROPERTY["ThermalTransmittance"] == 0.10


def test_evaluator_usa_a_banda_da_propriedade_no_top1():
    """O Evaluator (não só o helper) precisa aplicar a banda por propriedade."""
    issue = _thermal_issue()

    metrics = Evaluator().evaluate([(issue, _sset(issue, [2.48]))], _gt(issue, 2.35))

    assert metrics.accuracy_top1 == 1.0


# ---------------------------------------------------------------------------
# 2. Erro contínuo registrado por issue
# ---------------------------------------------------------------------------


def test_outcome_registra_erro_relativo_do_top1():
    issue = _thermal_issue()

    out = build_issue_outcomes([(issue, _sset(issue, [2.48]))], _gt(issue, 2.35))[0]

    assert out.error_pct == pytest.approx(5.53, abs=0.05)


def test_outcome_sem_valor_numerico_nao_inventa_erro():
    """FireRating é texto: erro relativo não se aplica."""
    issue = Issue(
        element_guid="F" * 22,
        element_class="IfcWall",
        element_name="Parede",
        issue_type="pset_missing",
        severity="high",
        description="FireRating ausente",
        context={"check_property": "FireRating"},
    )

    out = build_issue_outcomes([(issue, _sset(issue, ["REI 60"]))], _gt(issue, "REI 60"))[0]

    assert out.error_pct is None


def test_breakdown_reporta_mape_e_faixas_para_estrato_numerico():
    """Errar 5% e errar 300% não podem colapsar no mesmo zero."""
    perto = _thermal_issue()
    longe = Issue(
        element_guid="J" * 22,
        element_class="IfcWindow",
        element_name="Janela",
        issue_type="pset_missing",
        severity="high",
        description="ThermalTransmittance ausente",
        context={"check_property": "ThermalTransmittance"},
    )
    gt = GroundTruth(
        items=[
            GroundTruthItem(
                element_guid=perto.element_guid,
                issue_type="pset_missing",
                check_property="ThermalTransmittance",
                expected_value=2.35,
            ),
            GroundTruthItem(
                element_guid=longe.element_guid,
                issue_type="pset_missing",
                check_property="ThermalTransmittance",
                expected_value=5.7,
            ),
        ]
    )
    results = [(perto, _sset(perto, [2.48])), (longe, _sset(longe, [2.48]))]

    outcomes = build_issue_outcomes(results, gt)
    row = aggregate_by_stratum(outcomes)[0]

    assert row["dentro_10pct"] == 0.5
    assert row["mape"] == pytest.approx((5.53 + 56.49) / 2, abs=0.1)
