"""Faixa física de plausibilidade das grandezas contínuas sugeridas pelo LLM.

Medido em 2026-07-27: o ``qwen3.5:9b`` propôs ``U = 10,0 W/(m²·K)`` para uma
parede cujo valor calculado é 2,35, e ``U = 0,35`` para uma janela — os dois com
``confidence: alta``. Nenhum elemento construtivo atinge 10; 0,35 é vidraça com
desempenho de parede super-isolada. São erros que a física descarta sem precisar
do ground truth, e portanto o pipeline pode filtrar sozinho.

Princípio: **rebaixar, nunca descartar.** Esvaziar a lista de opções foi
exatamente o bug que zerou o dataset mascarado; abstenção aqui se declara com
``review_required``, não devolvendo lista vazia.
"""

from __future__ import annotations

from src.models import Issue

# (mínimo, máximo) fisicamente defensável por propriedade.
#
# ThermalTransmittance: o piso é parede com isolamento pesado (~0,2); o teto é
# vidro simples em caixilho metálico sem ruptura térmica (~6,0), com folga até
# 7,0 para esquadria de vidro fino. Fora disso não existe elemento construtivo.
PLAUSIBLE_RANGES: dict[str, tuple[float, float]] = {
    "ThermalTransmittance": (0.2, 7.0),
    "SolarHeatGainCoefficient": (0.05, 1.0),
    "VisibleTransmittance": (0.05, 1.0),
}

# Componente envidraçado tem física própria: o melhor vidro triplo Low-E do
# mercado fica em torno de 0,8 W/(m²·K) — abaixo disso não existe esquadria, por
# mais que exista parede. Sem o recorte por classe, ``U = 0,35`` numa janela
# passava por plausível.
_GLAZED_CLASSES = frozenset({"IfcWindow", "IfcCurtainWall", "IfcPlate"})
_RANGES_BY_CLASS: dict[str, dict[str, tuple[float, float]]] = {
    "ThermalTransmittance": {classe: (0.8, 7.0) for classe in _GLAZED_CLASSES},
}


def plausible_range_for(issue: Issue) -> tuple[float, float] | None:
    """Faixa aplicável à propriedade da issue, ou None se não houver.

    A faixa por classe tem precedência sobre a geral quando existe.
    """
    check_property = str(issue.context.get("check_property") or "").strip()
    por_classe = _RANGES_BY_CLASS.get(check_property, {})
    especifica = por_classe.get(issue.element_class)
    if especifica is not None:
        return especifica
    return PLAUSIBLE_RANGES.get(check_property)


def is_physically_plausible(issue: Issue, value: object) -> bool:
    """True se o valor cabe na física da propriedade (ou se não há faixa aplicável).

    Valor não numérico numa propriedade numérica não é reprovado aqui: quem
    cuida de tipo é a validação de schema. Este filtro responde só a pergunta
    "esse número existe no mundo?".
    """
    faixa = plausible_range_for(issue)
    if faixa is None:
        return True
    try:
        numero = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return True
    minimo, maximo = faixa
    return minimo <= numero <= maximo
