"""Duas correções derivadas da medição de 2026-07-27 (run ``evidencia``).

**Montante metálico.** Dar o método de cálculo sem a regra do montante fez o
modelo tratar 7 cm de perfil de aço como isolante: respondeu U = 1,23 para a
parede de drywall cujo valor calculado é 2,35 (antes respondia 2,48). As camadas
reais são ``Gesso 1,5 cm + Metal 7 cm + Gesso 1,5 cm``; a NBR 15220-2 trata o
vazio entre montantes como câmara de ar não ventilada (R ≈ 0,17), e metal
conduz — não isola.

**Priming negativo.** A instrução ``NÃO traduza para português`` fez o modelo
começar a traduzir: ``SALA DE ESTAR``, ``BANHEIRO``, ``APARTAMENTO`` onde antes
acertava ``CIRCULATION``. Mencionar a proibição introduziu a ideia. A restrição
passa a ser afirmativa.
"""

from __future__ import annotations

from src.models import Issue
from src.suggestion_engine.prompt_templates import build_prompt

_BUILDING_CTX = {"building_type": "Residencial multifamiliar", "bioclimatic_zone": "3"}


def _issue(prop: str, element_class: str = "IfcWall", **context) -> Issue:
    base = {"check_property": prop, "pset_name": "Pset_WallCommon"}
    base.update(context)
    return Issue(
        element_guid="E" * 22,
        element_class=element_class,
        element_name="Elemento",
        issue_type="pset_missing",
        severity="high",
        description=f"{prop} ausente",
        context=base,
    )


# ---------------------------------------------------------------------------
# Montante metálico não é isolante
# ---------------------------------------------------------------------------


def test_termico_de_parede_ensina_a_camara_de_ar_do_drywall():
    issue = _issue(
        "ThermalTransmittance",
        material_name="Dry-Wall 10cm",
        layers=[
            {"material": "Gesso Acartonado", "thickness_m": 0.015},
            {"material": "Metal", "thickness_m": 0.07},
            {"material": "Gesso Acartonado", "thickness_m": 0.015},
        ],
    )

    _, user = build_prompt(issue, _BUILDING_CTX)

    texto = user.lower()
    assert "montante" in texto, "sem a regra do montante o modelo isola com aço"
    assert "não isola" in texto or "nao isola" in texto
    assert "0,17" in user, "sem R da câmara de ar o cálculo não fecha"


def test_regra_vale_para_o_template_de_laje_tambem():
    """Laje com vazio (nervurada, EPS entre vigotas) tem o mesmo risco."""
    issue = _issue("ThermalTransmittance", element_class="IfcSlab", material_name="laje")

    _, user = build_prompt(issue, _BUILDING_CTX)

    assert "metal" in user.lower(), "template de laje não avisa sobre metal condutor"


def test_lambda_do_metal_nao_e_apresentado_como_isolante():
    """Se listar λ do aço, precisa deixar claro que é altíssimo (conduz)."""
    issue = _issue("ThermalTransmittance", material_name="Dry-Wall")

    _, user = build_prompt(issue, _BUILDING_CTX)

    assert "aço" in user.lower() or "metal" in user.lower()


# ---------------------------------------------------------------------------
# Category sem instrução negativa
# ---------------------------------------------------------------------------


def _space_issue() -> Issue:
    return Issue(
        element_guid="S" * 22,
        element_class="IfcSpace",
        element_name="43",
        issue_type="pset_missing",
        severity="medium",
        description="Category ausente",
        context={"check_property": "Category", "area_m2": 12.0, "contained_elements": []},
    )


def test_category_nao_menciona_traducao():
    """Citar 'não traduza para português' foi o que induziu a tradução."""
    _, user = build_prompt(_space_issue(), _BUILDING_CTX)

    texto = user.lower()
    assert "traduz" not in texto, "a proibição de traduzir voltou a primar o modelo"
    assert "português" not in texto and "portugues" not in texto


def test_category_mantem_restricao_afirmativa():
    _, user = build_prompt(_space_issue(), _BUILDING_CTX)

    assert "EXATAMENTE" in user or "exatamente" in user
    assert "TECHNICAL_AREA" in user, "vocabulário precisa continuar visível"


def test_category_nao_lista_exemplo_que_ancora():
    """O placeholder não pode ser um token real da lista."""
    _, user = build_prompt(_space_issue(), _BUILDING_CTX)

    assert '"valor": "BEDROOM"' not in user
