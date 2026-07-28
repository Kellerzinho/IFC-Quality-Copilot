"""Valor categórico não pode ser comparado como número.

Descoberto em 2026-07-27 ao investigar o estrato de ``FireRating`` (1020 itens,
40% do ground truth do prédio). ``_compare_normalized`` extraía o número de
qualquer string, então ``"EI 60"``, ``"R 60"`` e ``"REI 60"`` viravam ``60.0`` e
casavam entre si. A aritmética confirma que era isso que a métrica media:

- modelo respondendo sempre ``REI 60`` → durações 60 → 798/1020 = 0,782
- modelo respondendo ``EI 30/60/90``  → durações 30/60 → 526/1020 = 0,516

Para o engenheiro as classes são distintas: ``R`` é resistência mecânica
(elemento portante), ``E`` estanqueidade, ``I`` isolamento térmico. Uma parede
``EI 60`` NÃO cumpre um requisito ``REI 60``.

É a mesma família de defeito que já havia sido corrigida no cálculo de MAPE
(``"REI 60"`` parseia como 60 e contaminava estrato categórico) — aqui na
comparação que decide o acerto.
"""

from __future__ import annotations

import pytest

from src.experiment.evaluator import Evaluator, GroundTruth, GroundTruthItem, values_match
from src.models import Issue, Suggestion, SuggestionSet


def _fire_issue() -> Issue:
    return Issue(
        element_guid="W" * 22,
        element_class="IfcWall",
        element_name="Parede",
        issue_type="pset_missing",
        severity="high",
        description="FireRating ausente",
        context={"check_property": "FireRating", "check_pset": "Pset_WallCommon"},
    )


def _thermal_issue() -> Issue:
    return Issue(
        element_guid="T" * 22,
        element_class="IfcWall",
        element_name="Parede",
        issue_type="pset_missing",
        severity="high",
        description="ThermalTransmittance ausente",
        context={"check_property": "ThermalTransmittance"},
    )


# ---------------------------------------------------------------------------
# Classe de resistência ao fogo é categórica
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("candidato", "esperado"),
    [("EI 60", "REI 60"), ("R 60", "REI 60"), ("REI 60", "EI 60"), ("E 30", "EI 30")],
)
def test_classes_diferentes_com_mesma_duracao_nao_casam(candidato, esperado):
    assert not values_match(_fire_issue(), candidato, esperado)


@pytest.mark.parametrize("valor", ["REI 60", "EI 30", "R 90"])
def test_classe_identica_casa(valor):
    assert values_match(_fire_issue(), valor, valor)


def test_duracoes_diferentes_na_mesma_classe_nao_casam():
    assert not values_match(_fire_issue(), "REI 30", "REI 60")


def test_grafia_e_acento_continuam_tolerados():
    """A correção mira semântica, não formatação."""
    assert values_match(_fire_issue(), "rei 60", "REI 60")


# ---------------------------------------------------------------------------
# Grandeza numérica continua numérica (o LLM devolve string)
# ---------------------------------------------------------------------------


def test_numero_em_texto_ainda_casa_numero():
    """O LLM devolve "2.48"; o GT guarda 2.35 float — comparação numérica vale."""
    assert values_match(_thermal_issue(), "2.38", 2.35)


def test_numero_fora_da_banda_nao_casa():
    assert not values_match(_thermal_issue(), "1.23", 2.35)


def test_categoria_de_espaco_e_categorica():
    issue = Issue(
        element_guid="S" * 22,
        element_class="IfcSpace",
        element_name="Sala",
        issue_type="pset_missing",
        severity="medium",
        description="Category ausente",
        context={"check_property": "Category"},
    )

    assert values_match(issue, "BEDROOM", "BEDROOM")
    assert not values_match(issue, "KITCHEN", "BEDROOM")


# ---------------------------------------------------------------------------
# Efeito no Evaluator (é o número que vai para o artigo)
# ---------------------------------------------------------------------------


def test_evaluator_deixa_de_premiar_classe_errada():
    issue = _fire_issue()
    gt = GroundTruth(
        items=[
            GroundTruthItem(
                element_guid=issue.element_guid,
                issue_type="pset_missing",
                check_property="FireRating",
                expected_value="REI 60",
                accepted_alternatives=["REI 90"],
            )
        ]
    )
    sset = SuggestionSet(
        issue_id=issue.id,
        suggestions=[
            Suggestion(label="EI 60", value="EI 60", justification="j", confidence="alta")
        ],
    )

    metrics = Evaluator().evaluate([(issue, sset)], gt)

    assert metrics.accuracy_top1 == 0.0, "classe errada continuou pontuando como acerto"
