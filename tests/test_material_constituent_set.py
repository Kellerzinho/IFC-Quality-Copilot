"""Leitura de material no formato que o Revit exporta (item B).

Medido em 2026-07-27 no modelo do prédio: **867 das 887** issues de
``system_unclassified`` chegavam ao LLM com ``materials=[]`` e
``total_thickness=None``, e **606 de 606** issues de ``ThermalTransmittance``
com ``thickness_m=None``. O dado existe no IFC — o Revit exporta
``IfcMaterialConstituentSet``, e os extratores só entendiam
``IfcMaterialLayerSet``/``LayerSetUsage``.

A espessura de cada constituinte não fica no material (``IfcMaterialConstituent``
não tem espessura) e sim no conjunto de quantidades, como
``IfcPhysicalComplexQuantity`` com ``Discrimination='Layer'``; a espessura total
fica em ``Width`` (paredes) ou ``Depth`` (lajes).
"""

from __future__ import annotations

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.guid
import pytest

from src.ifc_analyzer.material_reader import read_material_layers

_CAMADAS = [
    (".massa corrida e pintura", 0.02),
    (".alvenaria deitado 18 cm", 0.16),
    (".massa corrida e pintura (2)", 0.02),
]


@pytest.fixture
def wall_com_constituent_set() -> tuple[ifcopenshell.file, ifcopenshell.entity_instance]:
    """IfcWall com IfcMaterialConstituentSet + Qto com espessura por camada."""
    f = ifcopenshell.file(schema="IFC4")
    wall = f.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name="parede interna 20cm")

    constituents = []
    for nome, _ in _CAMADAS:
        material = f.create_entity("IfcMaterial", Name=nome)
        constituents.append(f.create_entity("IfcMaterialConstituent", Name=nome, Material=material))
    constituent_set = f.create_entity(
        "IfcMaterialConstituentSet", Name="parede interna 20cm", MaterialConstituents=constituents
    )
    f.create_entity(
        "IfcRelAssociatesMaterial",
        GlobalId=ifcopenshell.guid.new(),
        RelatedObjects=[wall],
        RelatingMaterial=constituent_set,
    )

    # Qto: uma IfcPhysicalComplexQuantity por camada + Width total
    quantities = []
    for nome, espessura in _CAMADAS:
        largura = f.create_entity("IfcQuantityLength", Name="Width", LengthValue=espessura)
        quantities.append(
            f.create_entity(
                "IfcPhysicalComplexQuantity",
                Name=nome,
                HasQuantities=[largura],
                Discrimination="Layer",
            )
        )
    quantities.append(f.create_entity("IfcQuantityLength", Name="Width", LengthValue=0.20))
    qto = f.create_entity(
        "IfcElementQuantity",
        GlobalId=ifcopenshell.guid.new(),
        Name="Qto_WallBaseQuantities",
        Quantities=quantities,
    )
    f.create_entity(
        "IfcRelDefinesByProperties",
        GlobalId=ifcopenshell.guid.new(),
        RelatedObjects=[wall],
        RelatingPropertyDefinition=qto,
    )
    return f, wall


@pytest.fixture
def wall_com_layer_set() -> tuple[ifcopenshell.file, ifcopenshell.entity_instance]:
    """IfcWall no formato clássico IfcMaterialLayerSet (regressão)."""
    f = ifcopenshell.file(schema="IFC4")
    wall = f.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name="parede layerset")
    layers = [
        f.create_entity(
            "IfcMaterialLayer",
            Material=f.create_entity("IfcMaterial", Name=nome),
            LayerThickness=espessura,
        )
        for nome, espessura in _CAMADAS
    ]
    layer_set = f.create_entity("IfcMaterialLayerSet", MaterialLayers=layers, LayerSetName="LS")
    f.create_entity(
        "IfcRelAssociatesMaterial",
        GlobalId=ifcopenshell.guid.new(),
        RelatedObjects=[wall],
        RelatingMaterial=layer_set,
    )
    return f, wall


# ---------------------------------------------------------------------------
# ConstituentSet (formato do Revit)
# ---------------------------------------------------------------------------


def test_le_nomes_dos_constituintes(wall_com_constituent_set):
    """Os nomes das camadas são a evidência que o LLM precisa para classificar."""
    _, wall = wall_com_constituent_set

    leitura = read_material_layers(wall)

    assert [c["name"] for c in leitura.layers] == [nome for nome, _ in _CAMADAS]


def test_espessura_por_camada_vem_do_conjunto_de_quantidades(wall_com_constituent_set):
    """IfcMaterialConstituent não guarda espessura; ela está no Qto por camada."""
    _, wall = wall_com_constituent_set

    leitura = read_material_layers(wall)

    assert [c["thickness_m"] for c in leitura.layers] == [0.02, 0.16, 0.02]


def test_espessura_total_vem_do_width_do_qto(wall_com_constituent_set):
    _, wall = wall_com_constituent_set

    leitura = read_material_layers(wall)

    assert leitura.total_thickness_m == pytest.approx(0.20)


def test_nome_do_material_e_o_do_conjunto(wall_com_constituent_set):
    _, wall = wall_com_constituent_set

    leitura = read_material_layers(wall)

    assert leitura.material_name == "parede interna 20cm"


# ---------------------------------------------------------------------------
# LayerSet clássico continua funcionando
# ---------------------------------------------------------------------------


def test_layer_set_classico_continua_lido(wall_com_layer_set):
    _, wall = wall_com_layer_set

    leitura = read_material_layers(wall)

    assert [c["name"] for c in leitura.layers] == [nome for nome, _ in _CAMADAS]
    assert [c["thickness_m"] for c in leitura.layers] == [0.02, 0.16, 0.02]
    assert leitura.total_thickness_m == pytest.approx(0.20)


def test_elemento_sem_material_nao_quebra():
    f = ifcopenshell.file(schema="IFC4")
    wall = f.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name="sem material")

    leitura = read_material_layers(wall)

    assert leitura.layers == []
    assert leitura.total_thickness_m is None
    assert leitura.material_name is None


# ---------------------------------------------------------------------------
# Integração: os dois diagnósticos que estavam cegos
# ---------------------------------------------------------------------------


def test_system_diagnostics_recebe_camadas_do_constituent_set(wall_com_constituent_set):
    """A issue de sistema construtivo precisa carregar as camadas no context."""
    from src.ifc_analyzer.system_diagnostics import _extract_material_layers

    _, wall = wall_com_constituent_set

    layers = _extract_material_layers(wall)

    assert [c["name"] for c in layers] == [nome for nome, _ in _CAMADAS]


def test_thermal_extractor_recebe_material_e_espessura(wall_com_constituent_set):
    """Sem espessura o modelo não tem como calcular U."""
    from src.ifc_analyzer.extractors.thermal_extractor import _extract_material_layers

    _, wall = wall_com_constituent_set

    material_name, layers, total = _extract_material_layers(wall)

    assert material_name == "parede interna 20cm"
    assert len(layers) == 3
    assert total == pytest.approx(0.20)


def test_pset_diagnostics_preenche_espessura_da_issue(wall_com_constituent_set):
    """É o pset_diagnostics que monta o context de ThermalTransmittance/FireRating.

    Era o quinto ponto do código a ler material por conta própria — e o que
    deixava ``thickness_m=None`` nas 606 issues de transmitância do prédio.
    """
    from src.ifc_analyzer.pset_diagnostics import _extract_element_material_context

    f, wall = wall_com_constituent_set

    context = _extract_element_material_context(wall, f)

    assert context["material_name"] == "parede interna 20cm"
    assert context["thickness_m"] == pytest.approx(0.20)
    assert len(context["layers"]) == 3
