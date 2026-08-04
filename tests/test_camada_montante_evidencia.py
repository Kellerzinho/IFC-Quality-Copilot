"""Montante metálico chega ao prompt como câmara de ar (correção P1, 2026-08-04).

Medido no smoke do v7, estímulo do drywall (222 issues, 40% do estrato térmico):
o modelo devolveu 3,5019, cujo R implícito é **0,2856** — exatamente
``0,13 + 0,02/0,35 + 0,07/55 + 0,02/0,35 + 0,04``. Ou seja, aplicou λ = 55 na
camada de metal em vez de tratá-la como câmara de ar.

O template dizia as duas coisas: ``aço/metal 55`` na **tabela de λ** e "trate
essa camada como CÂMARA DE AR de R ≈ 0,17" em **prosa**. O modelo seguiu a
tabela. É o mesmo padrão de todos os achados da semana — **evidência tabular
ganha de instrução em prosa** — então a correção é entregar a leitura como
EVIDÊNCIA, não escrever a instrução mais forte.

Com as espessuras como o IFC declara, seguir a câmara de ar dá U = 2,20 contra
GT 2,35: **6,3%, dentro da banda de 10%**. O estímulo é recuperável.
"""

from __future__ import annotations

from src.suggestion_engine.prompt_templates import _format_material_layers

_DRYWALL = [
    {"name": "NormaDOM - Gesso Acartonado 10", "thickness_m": 0.02},
    {"name": "NormaDOM - Metal", "thickness_m": 0.07},
    {"name": "NormaDOM - Gesso Acartonado 10", "thickness_m": 0.02},
]


def test_internal_metal_layer_is_labelled_as_air_cavity():
    """A camada de montante chega nomeada, não como 'Metal' cru."""
    texto = _format_material_layers(_DRYWALL)

    assert "câmara de ar" in texto.lower()
    assert "0,17" in texto or "0.17" in texto


def test_outer_metal_layer_is_not_relabelled():
    """Chapa metálica externa é metal de verdade — não é montante."""
    camadas = [
        {"name": "Chapa de Aço", "thickness_m": 0.005},
        {"name": "Concreto", "thickness_m": 0.10},
    ]

    assert "câmara de ar" not in _format_material_layers(camadas).lower()


def test_single_metal_layer_is_not_relabelled():
    """Uma camada só não forma cavidade entre montantes."""
    assert "câmara" not in _format_material_layers(
        [{"name": "Metal", "thickness_m": 0.07}]
    ).lower()


def test_non_metal_internal_layer_is_untouched():
    """Núcleo isolante continua sendo isolante."""
    camadas = [
        {"name": "Gesso", "thickness_m": 0.0125},
        {"name": "Lã de Rocha", "thickness_m": 0.05},
        {"name": "Gesso", "thickness_m": 0.0125},
    ]
    texto = _format_material_layers(camadas)

    assert "câmara de ar" not in texto.lower()
    assert "Lã de Rocha" in texto


def test_layer_names_and_thicknesses_are_preserved():
    """A anotação acrescenta leitura; não apaga a evidência original."""
    texto = _format_material_layers(_DRYWALL)

    assert "NormaDOM - Metal" in texto
    assert "(7cm)" in texto
    assert texto.count("Gesso Acartonado") == 2
