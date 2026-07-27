"""Faixa física de plausibilidade para grandezas contínuas.

Medido em 2026-07-27: o ``qwen3.5:9b`` propôs **U = 10,0 W/(m²·K)** para uma
parede (valor calculado 2,35) e **U = 0,35** para uma janela — ambos com
``confidence: alta``. Dez é ordem de grandeza que nenhum elemento construtivo
atinge; 0,35 é vidraça com desempenho de parede super-isolada.

O filtro não descarta a opção (esvaziar a lista foi o bug que zerou o dataset
mascarado): rebaixa a confiança e marca revisão. Como ``_validate_suggestions``
ordena por confiança, uma opção implausível em 1º cede lugar a uma plausível —
é assim que o filtro vira acerto de top-1, não só um aviso.
"""

from __future__ import annotations

import pytest

from src.models import Issue, Suggestion
from src.suggestion_engine.plausibility import (
    PLAUSIBLE_RANGES,
    is_physically_plausible,
    plausible_range_for,
)


def _issue(prop: str, element_class: str = "IfcWall") -> Issue:
    return Issue(
        element_guid="E" * 22,
        element_class=element_class,
        element_name="Elemento",
        issue_type="pset_missing",
        severity="high",
        description=f"{prop} ausente",
        context={"check_property": prop},
    )


def _sug(value) -> Suggestion:
    return Suggestion(label=str(value), value=value, justification="j", confidence="alta")


# ---------------------------------------------------------------------------
# Faixa por propriedade
# ---------------------------------------------------------------------------


def test_transmitancia_tem_faixa_declarada():
    assert "ThermalTransmittance" in PLAUSIBLE_RANGES
    minimo, maximo = PLAUSIBLE_RANGES["ThermalTransmittance"]
    assert minimo > 0
    assert 6.0 <= maximo <= 8.0, "teto precisa acomodar vidro simples com caixilho metálico"


@pytest.mark.parametrize("valor", [2.35, 3.2, 5.7, 0.5])
def test_valores_de_engenharia_passam(valor):
    assert is_physically_plausible(_issue("ThermalTransmittance"), valor)


@pytest.mark.parametrize("valor", [10.0, 0.01, -1.0, 250.0])
def test_valores_absurdos_sao_reprovados(valor):
    assert not is_physically_plausible(_issue("ThermalTransmittance"), valor)


def test_propriedade_sem_faixa_nao_e_barrada():
    """Só filtramos o que sabemos limitar; o resto passa."""
    assert plausible_range_for(_issue("FireRating")) is None
    assert is_physically_plausible(_issue("FireRating"), "REI 60")


def test_valor_nao_numerico_em_propriedade_numerica_nao_quebra():
    assert is_physically_plausible(_issue("ThermalTransmittance"), "sem valor")


def test_fracoes_adimensionais_tem_faixa_de_zero_a_um():
    assert is_physically_plausible(_issue("SolarHeatGainCoefficient"), 0.87)
    assert not is_physically_plausible(_issue("SolarHeatGainCoefficient"), 1.4)


# ---------------------------------------------------------------------------
# Efeito na ordenação (é onde vira top-1)
# ---------------------------------------------------------------------------


def test_opcao_implausivel_perde_o_primeiro_lugar():
    """``['0.35', '1.2', '5.8']`` numa janela: 0,35 não existe em esquadria.

    O filtro não sabe qual das plausíveis é a certa — 1,2 (triplo Low-E) e 5,8
    (vidro simples) são ambas possíveis. O que ele garante é que a fisicamente
    impossível não ocupe o primeiro lugar.
    """
    from src.suggestion_engine.suggestion import SuggestionGenerator

    class _Cliente:
        model = "spy"

        def generate(self, prompt, system=None):
            return (
                '{"opcoes":[{"valor":0.35,"justificativa":"a","confianca":"alta"},'
                '{"valor":1.2,"justificativa":"b","confianca":"alta"},'
                '{"valor":5.8,"justificativa":"c","confianca":"alta"}]}',
                {},
            )

    issue = _issue("ThermalTransmittance", element_class="IfcWindow")
    resultado = SuggestionGenerator(_Cliente()).generate(issue, {})

    assert resultado.suggestions
    topo = float(resultado.suggestions[0].value)
    assert topo != pytest.approx(0.35), "opção fisicamente impossível continuou em primeiro"
    assert is_physically_plausible(issue, topo)


def test_implausivel_e_rebaixada_e_marcada_para_revisao():
    from src.suggestion_engine.suggestion import SuggestionGenerator

    class _Cliente:
        model = "spy"

        def generate(self, prompt, system=None):
            return '{"opcoes":[{"valor":10.0,"justificativa":"a","confianca":"alta"}]}', {}

    resultado = SuggestionGenerator(_Cliente()).generate(_issue("ThermalTransmittance"), {})

    assert resultado.suggestions, "opção implausível não pode ser descartada (esvaziaria a lista)"
    top = resultado.suggestions[0]
    assert top.confidence == "baixa"
    assert top.review_required is True
    assert "plausível" in top.justification or "plausivel" in top.justification
