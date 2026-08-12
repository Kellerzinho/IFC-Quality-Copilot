"""O prompt não pode entregar ao modelo o número que o ground truth espera.

Achado de 2026-08-10. O v7.3 removeu os limites da NBR 15575-5 do template de
laje porque "2,00" era exatamente o valor esperado de 19 itens — mas a mesma
classe de defeito sobreviveu no template solar, e em forma pior: o **exemplar
JSON de saída** trazia ``"valor": 0.87``, que é o valor esperado de 100% dos
134 itens de ``SolarHeatGainCoefficient``.

O mecanismo não é hipotético neste projeto. ``prompt_templates.py`` registra
que, quando janelas eram roteadas ao template de parede, "todos os modelos
respondiam ~2,48 (GT 5,7)": o modelo devolve o número que está no seu contexto.

Dois invariantes, com forças diferentes de propósito:

1. **Duro** — o exemplar de formato nunca carrega um valor numérico do GT. Um
   exemplar é espécime de forma; o próprio template de laje já avisa que "os
   números abaixo são PLACEHOLDER". Não há caso legítimo em contrário.
2. **Inventário** — os números do GT que aparecem no *corpo* do template (as
   tabelas de referência) ficam declarados um a um. Tabela de referência é
   grounding legítimo e medido (+31,2 pp na matriz v6), então não é proibida:
   é **declarada**, para que uma colisão nova apareça na revisão em vez de
   entrar em silêncio.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import pytest
import yaml

from src.suggestion_engine.prompt_templates import TEMPLATES

EVAL_DIR = Path(__file__).resolve().parents[1] / "data" / "evaluation"
_NUMBER = re.compile(r"\d+[.,]\d+")


@lru_cache(maxsize=1)
def _ground_truth_numbers() -> frozenset[float]:
    """Valores numéricos esperados nos dois ground truths congelados.

    Cacheado: são ~5 mil itens em YAML e o teste do exemplar é parametrizado
    por template.
    """
    values: set[float] = set()
    for dataset in ("predio", "casa"):
        path = EVAL_DIR / dataset / "ground_truth.yaml"
        if not path.exists():  # pragma: no cover - defesa para checkout parcial
            continue
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        for item in payload["items"]:
            expected = item.get("expected_value")
            try:
                values.add(float(str(expected).replace(",", ".")))
            except (TypeError, ValueError):
                continue
    return frozenset(values)


def _numbers_in(text: str) -> set[float]:
    return {float(raw.replace(",", ".")) for raw in _NUMBER.findall(text)}


def _exemplar_lines(template: str) -> list[str]:
    """Linhas do exemplar de formato JSON (as que declaram o contrato de saída)."""
    return [line for line in template.splitlines() if '"opcoes"' in line]


# ---------------------------------------------------------------------------
# 1. Invariante duro: exemplar de formato não carrega valor do ground truth
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(TEMPLATES))
def test_exemplar_de_formato_nao_carrega_valor_do_ground_truth(name: str) -> None:
    gt_numbers = _ground_truth_numbers()
    assert gt_numbers, "ground truth congelado não foi encontrado"

    for line in _exemplar_lines(TEMPLATES[name]):
        vazados = _numbers_in(line) & gt_numbers
        assert not vazados, (
            f"o exemplar JSON de {name!r} entrega {sorted(vazados)}, que é valor "
            f"esperado no ground truth — use placeholder (<numero>) como fazem os "
            f"demais templates:\n  {line.strip()}"
        )


# ---------------------------------------------------------------------------
# 1b. Exemplar também não pode semear resposta TEXTUAL
# ---------------------------------------------------------------------------

_PLACEHOLDER = re.compile(r"<[^>]+>|\.\.\.|N/A")
"""Marcas de campo a preencher: ``<numero>``, ``<TOKEN_DA_LISTA>``, ``"..."``."""

_CAMPOS_DE_VALOR = ("valor", "sistema", "nome")
"""Campos do contrato que carregam a resposta — os únicos que precisam ser vazios."""


@pytest.mark.parametrize("name", sorted(TEMPLATES))
def test_exemplar_de_formato_nao_semeia_resposta_textual(name: str) -> None:
    """O exemplar declara a FORMA da resposta, nunca uma resposta plausível.

    O invariante numérico acima não pegava âncora textual, e por isso duas
    passaram despercebidas até 2026-08-12: ``relation_fills_missing`` trazia
    ``"valor": "Verificar se o elemento foi inserido diretamente na parede..."``
    — que os modelos parafrasearam em vez de responder o nome da relação — e
    ``system_unclassified_structural`` trazia um rótulo concreto de viga no
    lugar do placeholder.
    """
    for line in _exemplar_lines(TEMPLATES[name]):
        for campo in _CAMPOS_DE_VALOR:
            for bruto in re.findall(rf'"{campo}"\s*:\s*"([^"]*)"', line):
                assert _PLACEHOLDER.search(bruto), (
                    f"o exemplar JSON de {name!r} entrega {bruto!r} no campo "
                    f"{campo!r}: exemplar declara forma, não resposta. Use um "
                    f"placeholder (<TOKEN_DA_LISTA>, <numero>, ...) como fazem "
                    f"os demais templates."
                )


# ---------------------------------------------------------------------------
# 2. Inventário declarado das colisões no corpo do template
# ---------------------------------------------------------------------------

# Cada entrada é uma decisão consciente, não um resíduo. Ao mexer nesta tabela,
# registre o motivo no doc de condição do PROMPT_VERSION correspondente.
COLISOES_DECLARADAS: dict[str, set[float]] = {
    # Tabela tipológica de vidros. É a única evidência que o estímulo tem: o
    # IFC não declara o vidro (o campo traz None ou o caixilho de alumínio).
    # Remover a tabela deixaria o modelo sem base alguma e mediria ruído, não
    # capacidade. Consequência declarada em docs/pontos-de-calculo.md §8: o
    # estrato SHGC mede concordância com a convenção adotada, não derivação.
    "pset_missing_solar": {0.87},
    # Faixas típicas de esquadria (vidro duplo 2,7 a 3,2; porta opaca 2,0 a
    # 3,0). Os números colidem com o GT de OUTRAS famílias (laje 3,2 e
    # cobertura 2,0), nunca com o da própria esquadria (5,7).
    "pset_missing_u_value_window": {2.0, 3.2},
}
# Nota de 2026-08-10: o template de parede (pset_missing_thermal) declara a
# faixa "1,5 a 3,5", que CONTÉM o U de parede do GT (2,35) sem citá-lo. Faixa de
# plausibilidade não é valor entregue, e nenhum dos seus extremos é valor
# esperado — por isso não entra neste inventário. A assimetria frente ao
# template de laje, desancorado no v7.3, fica anotada e sem ação.


def test_inventario_de_colisoes_numericas_esta_declarado() -> None:
    """Nenhuma colisão nova entre número do prompt e valor do GT, sem declaração."""
    gt_numbers = _ground_truth_numbers()
    encontradas: dict[str, set[float]] = {}
    for name, template in TEMPLATES.items():
        colisao = _numbers_in(template) & gt_numbers
        if colisao:
            encontradas[name] = colisao

    nao_declaradas = {
        name: sorted(values - COLISOES_DECLARADAS.get(name, set()))
        for name, values in encontradas.items()
        if values - COLISOES_DECLARADAS.get(name, set())
    }
    assert not nao_declaradas, (
        "colisão nova entre número do prompt e valor esperado do ground truth: "
        f"{nao_declaradas}. Decida e declare em COLISOES_DECLARADAS."
    )

    obsoletas = {
        name: sorted(values - encontradas.get(name, set()))
        for name, values in COLISOES_DECLARADAS.items()
        if values - encontradas.get(name, set())
    }
    assert not obsoletas, (
        f"declaração obsoleta em COLISOES_DECLARADAS: {obsoletas}. "
        "O número saiu do template; remova a entrada."
    )
