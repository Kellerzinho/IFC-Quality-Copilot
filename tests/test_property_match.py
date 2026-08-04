"""Testes do matcher compartilhado de nomes de propriedade IFC × bSDD.

O bSDD nomeia propriedades em forma humana ("Fire Rating", "Global ID");
o IDS e o IFC usam PascalCase ("FireRating"). Quatro consumidores comparavam
esses nomes literalmente e nunca casavam (no-op silencioso, revisão 2026-08-04):
grounding.prepare_llm_grounding, SuggestionGenerator._validate_against_bsdd,
normalization.resolve_bsdd_uri e QualityPipeline._default_bsdd_uri.
O matcher único elimina a divergência.
"""

from __future__ import annotations

import pytest

from src.semantic.property_match import (
    properties_match,
    property_match_key,
    strip_boolean_prefix,
)


@pytest.mark.parametrize(
    ("ifc_name", "bsdd_name"),
    [
        ("FireRating", "Fire Rating"),
        ("ThermalTransmittance", "Thermal Transmittance"),
        ("LoadBearing", "Load Bearing"),
        # Pset_WallCommon usa IsLoadBearing; o bSDD guarda a forma sem o
        # prefixo booleano (mesma regra já aplicada em _filter_properties).
        ("IsLoadBearing", "Load Bearing"),
        ("IsExternal", "External"),
        ("GlobalId", "Global ID"),
    ],
)
def test_ifc_pascalcase_matches_bsdd_human_form(ifc_name: str, bsdd_name: str) -> None:
    assert properties_match(ifc_name, bsdd_name)
    assert properties_match(bsdd_name, ifc_name)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("FireRating", "Fire Resistance"),
        ("ThermalTransmittance", "Thermal Transmittance Summer"),
        ("FireRating", ""),
        ("", ""),
    ],
)
def test_different_properties_do_not_match(a: str, b: str) -> None:
    assert not properties_match(a, b)


def test_match_key_ignores_case_and_separators() -> None:
    assert property_match_key("Fire Rating") == "firerating"
    assert property_match_key("FireRating") == "firerating"
    assert property_match_key("fire_rating") == "firerating"


def test_strip_boolean_prefix_only_on_normalized_keys() -> None:
    assert strip_boolean_prefix("isloadbearing") == "loadbearing"
    # Chaves curtas não são tratadas como booleanas prefixadas.
    assert strip_boolean_prefix("isex") == "isex"
