"""Um prompt, um contrato de saída (correção P0 de 2026-08-04).

Medido no smoke do v7: 11 rejeições de parse contra 0 no v6, todas com o modelo
respondendo no formato do bloco anexado (`label`, `canonical_term`, prosa no
lugar do número) em vez do formato do template. Causa: **os 20 templates já
declaram o próprio formato JSON**, e o `CONTRATO DE SAIDA` colado no fim
declarava um schema DIFERENTE — o modelo seguia o último que leu.

O fix de 26/07 unificou o contrato entre os quatro *caminhos* de prompt; esta é
a divergência que sobrou, entre **template e contrato anexado**.
"""

from __future__ import annotations

import pytest

from src.models import Issue
from src.suggestion_engine.prompt_templates import build_prompt

_CTX = {"building_type": "Residencial multifamiliar", "bioclimatic_zone": "3"}


def _issue(check_property: str, element_class: str = "IfcWall") -> Issue:
    return Issue(
        element_guid="W" * 22,
        element_class=element_class,
        element_name="Parede 01",
        issue_type="pset_missing",
        severity="high",
        description=f"{check_property} ausente",
        context={"check_pset": "Pset_WallCommon", "check_property": check_property},
    )


@pytest.mark.parametrize(
    ("check_property", "element_class"),
    [
        ("FireRating", "IfcWall"),
        ("ThermalTransmittance", "IfcWall"),
        ("ThermalTransmittance", "IfcSlab"),
        ("AcousticRating", "IfcWall"),
        ("LoadBearing", "IfcWall"),
    ],
)
def test_rich_prompt_declares_a_single_json_schema(check_property, element_class):
    """O prompt não pode pedir dois formatos de resposta diferentes."""
    _, user = build_prompt(_issue(check_property, element_class), _CTX)

    # O formato do template usa chaves em português; o schema genérico usava
    # "label"/"canonical_term". Os dois no mesmo prompt = contrato ambíguo.
    assert '"valor"' in user
    assert '"canonical_term"' not in user
    assert '"semantic_hint"' not in user
    assert '"source_candidates"' not in user


def test_rich_prompt_keeps_the_behavioural_rules():
    """O que o bloco anexado tinha de útil (abstenção, URI) permanece."""
    _, user = build_prompt(_issue("FireRating"), _CTX)

    assert "review_required" in user
    assert "URI" in user


def test_space_naming_prompt_still_has_a_single_schema():
    """space_unnamed usa o contrato próprio de nomeação — sem schema duplicado."""
    issue = Issue(
        element_guid="S" * 22,
        element_class="IfcSpace",
        element_name="Room 101",
        issue_type="space_unnamed",
        severity="low",
        description="sem nome",
        context={"current_name": "Room 101"},
    )

    _, user = build_prompt(issue, _CTX)

    assert '"canonical_term"' not in user
