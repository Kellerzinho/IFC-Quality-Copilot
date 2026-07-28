"""Evidência que falta no prompt e âncoras numéricas que viram resposta.

Auditoria de 2026-07-27 (censo dos 145 estímulos errados nos 3 modelos):

- **Âncoras.** Três templates continham valores que o modelo devolveu tal e qual:
  a tarefa do fogo lista ``"REI 60", "REI 90", "REI 120"`` e os três modelos
  responderam exatamente isso (GT ``EI 30``, 222 issues, 8,7 pp); o exemplo do
  térmico de parede é ``2.48`` e todos responderam 2,48; o de laje é ``1.80``
  junto de "piso ≤ 2,00" e todos responderam 1,8–2,0 (GT 3,2).
- **Evidência descartada.** ``_extract_element_material_context`` já extrai as
  camadas, mas o ``issue_context`` só copiava ``material_name`` e ``thickness_m``.
  ``LoadBearing`` e ``PredefinedType`` existem no IFC e nunca chegavam: o drywall
  do prédio tem ``LoadBearing=False`` (logo ``EI``, não ``REI``) e o telhado tem
  ``PredefinedType=ROOF``.
- **Esquadria tratada como parede.** ``IfcWindow`` caía no template de parede,
  com norma de parede e âncora de parede.
"""

from __future__ import annotations

import ifcopenshell
import ifcopenshell.guid
import pytest

from src.ifc_analyzer.pset_diagnostics import _check_element
from src.models import Issue
from src.suggestion_engine.prompt_templates import build_prompt

_BUILDING_CTX = {"building_type": "Residencial multifamiliar", "bioclimatic_zone": "3"}


def _issue(element_class: str, prop: str, **context) -> Issue:
    base = {"check_property": prop, "pset_name": f"Pset_{element_class[3:]}Common"}
    base.update(context)
    return Issue(
        element_guid="E" * 22,
        element_class=element_class,
        element_name=context.get("_nome", "Elemento"),
        issue_type="pset_missing",
        severity="high",
        description=f"{prop} ausente",
        context=base,
    )


# ---------------------------------------------------------------------------
# 1. Âncoras numéricas fora dos templates
# ---------------------------------------------------------------------------


def test_fogo_nao_ancora_o_modelo_em_rei():
    """A tarefa não pode exemplificar só REI: o drywall do prédio é EI 30."""
    issue = _issue("IfcWall", "FireRating", material_name="Dry-Wall 10cm", load_bearing=False)

    _, user = build_prompt(issue, _BUILDING_CTX)

    tarefa = user.split("TAREFA:")[1].split("\n")[0]
    assert '"REI 60", "REI 90", "REI 120"' not in tarefa, "tarefa ancora o modelo em REI"


def test_fogo_ensina_a_diferenca_entre_R_E_I():
    """Explica o critério R/E/I sem transformá-lo em regra rígida.

    Medido em 27/07: a versão com ``REGRA: se LoadBearing for False, o valor NÃO
    pode começar com R`` empurrou o modelo para EI em TODA parede e derrubou o
    estrato de 0,775 para 0,352 — inclusive nas paredes de alvenaria de
    compartimentação, que a prática brasileira especifica como REI. O critério
    continua no prompt; a decisão volta a ser do modelo, com material e
    espessura à vista.
    """
    issue = _issue("IfcWall", "FireRating", material_name="Dry-Wall 10cm", load_bearing=False)

    _, user = build_prompt(issue, _BUILDING_CTX)

    assert "EI" in user and "REI" in user
    assert "portante" in user.lower(), "prompt não explica quando cabe R (portante)"
    assert "NÃO pode começar com R" not in user, "regra rígida voltou"


def test_termico_de_laje_nao_exemplifica_um_valor_fixo():
    """O exemplo 1.80 virou resposta dos três modelos (GT 3,2)."""
    issue = _issue("IfcSlab", "ThermalTransmittance", material_name="laje de concreto")

    _, user = build_prompt(issue, _BUILDING_CTX)

    assert '"valor": 1.80' not in user
    assert '"valor": 1.8' not in user


def test_termico_de_laje_separa_limite_normativo_de_valor_medido():
    """O limite da norma é critério de conformidade, não estimativa do elemento."""
    issue = _issue("IfcSlab", "ThermalTransmittance", material_name="laje de concreto")

    _, user = build_prompt(issue, _BUILDING_CTX)

    texto = user.lower()
    assert "não é o valor" in texto or "nao e o valor" in texto, (
        "prompt não avisa que o limite normativo não é o valor do elemento"
    )


def test_termico_de_parede_nao_exemplifica_um_valor_fixo():
    issue = _issue("IfcWall", "ThermalTransmittance", material_name="parede interna 20cm")

    _, user = build_prompt(issue, _BUILDING_CTX)

    assert '"valor": 2.48' not in user


# ---------------------------------------------------------------------------
# 2. Evidência que existe no IFC e precisa chegar
# ---------------------------------------------------------------------------


def test_fogo_recebe_funcao_estrutural_e_camadas():
    issue = _issue(
        "IfcWall",
        "FireRating",
        material_name="Dry-Wall 10cm",
        load_bearing=False,
        is_external=True,
        thickness_m=0.1,
        layers=[{"material": "Gesso acartonado", "thickness_m": 0.015}],
    )

    _, user = build_prompt(issue, _BUILDING_CTX)

    assert "False" in user, "função estrutural (LoadBearing) ausente do prompt"
    assert "Gesso acartonado" in user, "camadas de material ausentes do prompt"
    assert "0.1" in user


def test_estrutural_recebe_predefined_type():
    """O telhado tem PredefinedType=ROOF; sem isso o modelo responde LoadBearing=True."""
    issue = _issue(
        "IfcSlab",
        "LoadBearing",
        material_name="Telha Fibrocimento",
        predefined_type="ROOF",
    )

    _, user = build_prompt(issue, _BUILDING_CTX)

    assert "ROOF" in user
    assert "cobertura" in user.lower(), "template não interpreta cobertura"


# ---------------------------------------------------------------------------
# 3. Esquadria não é parede
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("classe", ["IfcWindow", "IfcDoor"])
def test_esquadria_tem_template_proprio_de_transmitancia(classe):
    """Esquadria precisa da física do envidraçado, NÃO do valor exato do GT.

    O template dá a faixa de referência de vidro simples (5,5–6,0), que é
    conhecimento normativo corrente; cravar o 5,7 do ground truth no prompt
    seria ensinar a resposta ao modelo em vez de dar-lhe base para raciocinar.
    """
    issue = _issue(classe, "ThermalTransmittance", material_name="Janela Correr 2 Folhas")

    _, user = build_prompt(issue, _BUILDING_CTX)

    assert "5,5 a 6,0" in user, "sem faixa de referência para vidro simples"
    assert "5,7" not in user, "o valor exato do ground truth vazou para o prompt"
    assert "vidro" in user.lower()
    assert "NBR 15575-4 Tabela C.2" not in user, "usou a norma de paredes na esquadria"


def test_esquadria_nao_recebe_espessura_de_parede():
    """Largura do vão não é espessura de camada — não pode virar dado térmico."""
    issue = _issue("IfcWindow", "ThermalTransmittance", material_name="Janela", thickness_m=None)

    _, user = build_prompt(issue, _BUILDING_CTX)

    assert "Espessura total: 1.5" not in user


# ---------------------------------------------------------------------------
# 4. Vocabulário fechado (o modelo respondia BANHEIRO, Quarto, IFCLaJe...)
# ---------------------------------------------------------------------------


def test_category_exige_token_exato_do_vocabulario():
    """A restrição é afirmativa: 'copie exatamente', não 'não traduza'.

    A versão com proibição explícita foi medida em 27/07 e teve efeito contrário
    — mencionar 'não traduza para português' fez o modelo passar a responder
    ``SALA DE ESTAR``/``BANHEIRO``. Ver ``test_correcoes_prompt_medidas.py``.
    """
    issue = _issue("IfcSpace", "Category", area_m2=12.0, contained_elements=[])

    _, user = build_prompt(issue, _BUILDING_CTX)

    assert "EXATAMENTE" in user or "exatamente" in user
    assert "descartado" in user.lower(), "sem consequência declarada a restrição é frouxa"


def test_sistema_construtivo_exige_rotulo_da_lista():
    issue = Issue(
        element_guid="W" * 22,
        element_class="IfcWall",
        element_name="Parede",
        issue_type="system_unclassified",
        severity="medium",
        description="sem classificação",
        context={"materials": [{"name": "alvenaria", "thickness": 0.18}], "total_thickness": 0.2},
    )

    _, user = build_prompt(issue, _BUILDING_CTX)

    assert "exatamente" in user.lower(), "não exige rótulo idêntico ao da lista"


# ---------------------------------------------------------------------------
# 5. O diagnóstico precisa entregar a evidência (camadas/portante/tipo)
# ---------------------------------------------------------------------------


def _wall_com_pset() -> tuple[ifcopenshell.file, ifcopenshell.entity_instance]:
    f = ifcopenshell.file(schema="IFC4")
    wall = f.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name="Drywall")
    wall.PredefinedType = "STANDARD"
    material = f.create_entity("IfcMaterial", Name="Gesso acartonado")
    cset = f.create_entity(
        "IfcMaterialConstituentSet",
        Name="Dry-Wall 10cm",
        MaterialConstituents=[f.create_entity("IfcMaterialConstituent", Material=material)],
    )
    f.create_entity(
        "IfcRelAssociatesMaterial",
        GlobalId=ifcopenshell.guid.new(),
        RelatedObjects=[wall],
        RelatingMaterial=cset,
    )
    pset = f.create_entity(
        "IfcPropertySet",
        GlobalId=ifcopenshell.guid.new(),
        Name="Pset_WallCommon",
        HasProperties=[
            f.create_entity(
                "IfcPropertySingleValue",
                Name="LoadBearing",
                NominalValue=f.create_entity("IfcBoolean", False),
            ),
            f.create_entity(
                "IfcPropertySingleValue",
                Name="IsExternal",
                NominalValue=f.create_entity("IfcBoolean", True),
            ),
        ],
    )
    f.create_entity(
        "IfcRelDefinesByProperties",
        GlobalId=ifcopenshell.guid.new(),
        RelatedObjects=[wall],
        RelatingPropertyDefinition=pset,
    )
    return f, wall


def test_contexto_da_issue_carrega_camadas_portante_e_tipo():
    """As camadas já eram extraídas e descartadas; portante e tipo nem eram lidos."""
    f, wall = _wall_com_pset()
    issues: list[Issue] = []

    _check_element(wall, {"Pset_WallCommon": ["FireRating"]}, f, issues)

    assert issues, "issue de FireRating não foi criada"
    ctx = issues[0].context
    assert ctx["load_bearing"] is False
    assert ctx["predefined_type"] == "STANDARD"
    assert ctx["layers"], "camadas extraídas mas não repassadas ao contexto"
    assert ctx["layers"][0]["material"] == "Gesso acartonado"
