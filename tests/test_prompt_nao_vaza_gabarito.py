"""Guardrail: template de prompt não pode conter resposta do ground truth.

Motivado por três vazamentos que eu mesmo introduzi em 2026-07-27 ao corrigir
os prompts *depois* de olhar a lista de erros do modelo:

1. ``"laje maciça sem isolamento tem U real ENTRE 3,0 E 4,0"`` — o GT da laje
   em questão é 3,2. Isso é entregar a resposta.
2. ``"alvenaria de compartimentação costuma ser especificada como REI"`` —
   escrito depois de ver que o GT esperava ``REI 60``.
3. Tabela de ambientes de condomínio cuja *seleção* (medidores, hidrômetros,
   gás, lixo, cisterna, quadra, playground, guarita) saiu da lista de erros
   deste prédio — vocabulário legítimo, mas inútil num hospital ou galpão e
   ajustado ao gabarito.

O risco é sistêmico: qualquer ganho obtido assim não generaliza e, num artigo,
é resultado inflado. Este teste falha se um valor esperado do ground truth
aparecer literalmente num template.

**Exceção deliberada — vocabulário fechado.** Em ``Category`` e em
``system_unclassified`` a tarefa É escolher de uma lista, e a lista precisa
estar no prompt. O que se exige nesses casos é que ela seja COMPLETA (todos os
valores do GT presentes), não um subconjunto enviesado para a resposta.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from src.suggestion_engine.prompt_templates import TEMPLATES

_GT_DIR = Path(__file__).resolve().parent.parent / "data" / "evaluation" / "predio"

# Mapeamentos residenciais que JÁ EXISTIAM antes desta investigação (sofá → sala
# de estar, cama → dormitório). Também citam nomes que estão no ground truth, e
# a decisão de mantê-los ou não é de desenho do experimento: a tarefa de
# nomeação é de vocabulário aberto (modelo propõe) ou fechado (modelo escolhe de
# uma lista ensinada)? Ficam aqui explícitos, em vez de escondidos, até que essa
# decisão seja tomada.
_LEGADO_CONHECIDO: frozenset[str] = frozenset(
    {
        "Sala de Estar",
        "Sala de Jantar",
        "Cozinha",
        "Área de Serviço",
        "Despensa",
        "Sala",
        "Estar",
        "Jantar",
        "Serviço",
        "Banheiro",
        "Lavabo",
        "Dormitório",
        "Circulação",
    }
)
"""Termos da tabela residencial original (sofá → sala de estar, cama → dormitório).

A distinção que importa: esses vieram de conhecimento de projeto residencial,
escritos quando o template foi criado — não foram escolhidos depois de olhar as
respostas erradas do modelo. O que este teste barra é a segunda coisa.
"""


def _valores_esperados(arquivo: str) -> set[str]:
    """Valores textuais do ground truth (expected + alternativas aceitas)."""
    caminho = _GT_DIR / arquivo
    if not caminho.is_file():  # pragma: no cover - depende do dataset congelado
        pytest.skip(f"ground truth ausente: {caminho}")
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
    valores: set[str] = set()
    for item in dados.get("items") or []:
        for bruto in [item.get("expected_value"), *(item.get("accepted_alternatives") or [])]:
            if isinstance(bruto, str) and len(bruto.strip()) >= 4:
                valores.add(bruto.strip())
    return valores


def _templates_de_nomeacao() -> str:
    return TEMPLATES["space_unnamed"]


def _templates_termicos() -> str:
    return "\n".join(
        TEMPLATES[chave]
        for chave in ("pset_missing_thermal", "pset_missing_u_value_slab")
    )


# ---------------------------------------------------------------------------
# Nomes de ambiente
# ---------------------------------------------------------------------------


def test_template_de_nomeacao_nao_cita_nome_do_gabarito():
    """Citar o nome esperado transforma inferência em cópia."""
    esperados = _valores_esperados("ground_truth_spaces.yaml")
    texto = _templates_de_nomeacao().casefold()

    vazados = sorted(
        nome
        for nome in esperados
        if nome not in _LEGADO_CONHECIDO and nome.casefold() in texto
    )

    assert not vazados, f"nomes do ground truth presentes no template: {vazados}"


def test_inferencia_mapeia_equipamento_para_funcao_nao_para_nome():
    """O modelo deve derivar o nome, não recebê-lo pronto."""
    template = _templates_de_nomeacao()

    assert "INFERÊNCIA DE FUNÇÃO" in template
    assert "PARA QUE SERVE" in template, "a pista precisa ser o raciocínio, não o catálogo"
    assert "→ ambiente técnico" in template, "a pista precisa apontar função, não nome"
    # Nomear o equipamento também vaza: "churrasqueira" e "central de gás" são
    # alternativas aceitas no ground truth deste prédio.
    for equipamento in ("churrasqueira", "hidrômetro", "cisterna"):
        assert equipamento not in template.casefold()


# ---------------------------------------------------------------------------
# Grandezas numéricas
# ---------------------------------------------------------------------------


def test_template_termico_nao_afirma_faixa_do_elemento_analisado():
    """Regressão dos dois trechos removidos: eles cercavam o valor do GT."""
    texto = _templates_termicos()

    assert "ENTRE 3,0 E 4,0" not in texto
    assert "U real" not in texto


def test_template_termico_nao_contem_valor_esperado_do_gabarito():
    numeros = {
        float(item["expected_value"])
        for item in (yaml.safe_load((_GT_DIR / "ground_truth.yaml").read_text(encoding="utf-8")) or {}).get("items", [])
        if item.get("check_property") == "ThermalTransmittance"
        and isinstance(item.get("expected_value"), (int, float))
    }
    texto = _templates_termicos()
    presentes = {n for n in re.findall(r"\d+,\d+|\d+\.\d+", texto)}

    colisoes = sorted(
        valor
        for valor in presentes
        if float(valor.replace(",", ".")) in numeros
    )

    assert not colisoes, f"valores do ground truth térmico no template: {colisoes}"


# ---------------------------------------------------------------------------
# Resistência ao fogo
# ---------------------------------------------------------------------------


def test_template_de_fogo_nao_cita_classe_do_gabarito():
    esperados = {
        str(item["expected_value"])
        for item in (yaml.safe_load((_GT_DIR / "ground_truth.yaml").read_text(encoding="utf-8")) or {}).get("items", [])
        if item.get("check_property") == "FireRating"
    }
    texto = TEMPLATES["pset_missing_fire"]

    vazados = sorted(v for v in esperados if v and v in texto)

    assert not vazados, f"classes do ground truth no template de fogo: {vazados}"


def test_template_de_fogo_nao_sugere_pratica_que_replica_o_gabarito():
    texto = TEMPLATES["pset_missing_fire"]

    assert "costuma ser especificada como REI" not in texto


# ---------------------------------------------------------------------------
# Vocabulário fechado: exigir lista COMPLETA, não subconjunto enviesado
# ---------------------------------------------------------------------------


def test_vocabulario_de_category_e_completo():
    """Listar a lista toda é legítimo; listar um subconjunto seria dica."""
    esperados = {
        str(item["expected_value"])
        for item in (yaml.safe_load((_GT_DIR / "ground_truth.yaml").read_text(encoding="utf-8")) or {}).get("items", [])
        if item.get("check_property") == "Category"
    }
    texto = TEMPLATES["pset_missing_space_category"]

    ausentes = sorted(v for v in esperados if v and v not in texto)

    assert not ausentes, f"vocabulário incompleto favorece as opções listadas: {ausentes}"
