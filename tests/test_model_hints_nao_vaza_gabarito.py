"""Guardrail: o direcionamento por modelo não pode conter resposta do gabarito.

Extensão de ``tests/test_prompt_nao_vaza_gabarito.py`` para o módulo
``model_hints`` (v6): os hints foram escritos DEPOIS de analisar os erros do
benchmark 2026-07-28, exatamente a situação em que o vazamento acontece sem
intenção. As mesmas varreduras dos templates valem aqui, sem exceção de
vocabulário fechado — hint não carrega lista de valores.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from src.suggestion_engine.model_hints import all_hint_texts

_GT_DIR = Path(__file__).resolve().parent.parent / "data" / "evaluation" / "predio"

# Termos residenciais de conhecimento geral, já tolerados no template legado
# (ver test_prompt_nao_vaza_gabarito._LEGADO_CONHECIDO). Os hints nem deveriam
# precisar deles — a lista existe para o caso de um hint citar "circulação"
# como classe de função.
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


def _gt_yaml(arquivo: str) -> dict:
    caminho = _GT_DIR / arquivo
    if not caminho.is_file():  # pragma: no cover - depende do dataset congelado
        pytest.skip(f"ground truth ausente: {caminho}")
    return yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}


def _valores_textuais(arquivo: str) -> set[str]:
    valores: set[str] = set()
    for item in _gt_yaml(arquivo).get("items") or []:
        for bruto in [item.get("expected_value"), *(item.get("accepted_alternatives") or [])]:
            if isinstance(bruto, str) and len(bruto.strip()) >= 4:
                valores.add(bruto.strip())
    return valores


def _texto_dos_hints() -> str:
    return "\n".join(all_hint_texts()).casefold()


def test_hints_nao_citam_nome_de_ambiente_do_gabarito():
    esperados = _valores_textuais("ground_truth_spaces.yaml")
    texto = _texto_dos_hints()

    vazados = sorted(
        nome
        for nome in esperados
        if nome not in _LEGADO_CONHECIDO and nome.casefold() in texto
    )

    assert not vazados, f"nomes do ground truth presentes nos hints: {vazados}"


def test_hints_nao_citam_valor_textual_do_gabarito_do_predio():
    """Cobre FireRating (``REI 60``…), Category e sistemas construtivos."""
    esperados = _valores_textuais("ground_truth.yaml")
    texto = _texto_dos_hints()

    vazados = sorted(v for v in esperados if v.casefold() in texto)

    assert not vazados, f"valores do ground truth presentes nos hints: {vazados}"


def test_hints_nao_contem_numero_do_gabarito_termico():
    numeros = {
        float(item["expected_value"])
        for item in _gt_yaml("ground_truth.yaml").get("items", [])
        if item.get("check_property") == "ThermalTransmittance"
        and isinstance(item.get("expected_value"), (int, float))
    }
    texto = _texto_dos_hints()
    presentes = set(re.findall(r"\d+,\d+|\d+\.\d+", texto))

    colisoes = sorted(
        valor for valor in presentes if float(valor.replace(",", ".")) in numeros
    )

    assert not colisoes, f"valores do gabarito térmico nos hints: {colisoes}"


def test_hints_mapeiam_processo_e_nao_equipamento_para_nome():
    """Mesma regra do template: equipamento aceito como alternativa no GT não
    pode aparecer nomeado num hint."""
    texto = _texto_dos_hints()
    for equipamento in ("churrasqueira", "hidrômetro", "cisterna", "botijão"):
        assert equipamento not in texto, f"hint cita equipamento do gabarito: {equipamento}"
