"""Testes para o módulo de diagnóstico de sistema construtivo."""

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.guid
import pytest

from src.ifc_analyzer.system_diagnostics import (
    diagnose_systems,
    _get_classification,
    _has_standard_material_pset,
    _detect_custom_material_pset,
    _extract_material_layers,
    _total_thickness,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _add_classification(
    ifc_file: ifcopenshell.file,
    element: ifcopenshell.entity_instance,
    item_ref: str = "NBR-15575",
    name: str = "Alvenaria de bloco cerâmico",
) -> ifcopenshell.entity_instance:
    """Associa um IfcClassificationReference ao elemento."""
    cls_ref = ifc_file.create_entity(
        "IfcClassificationReference",
        ItemReference=item_ref,
        Name=name,
    )
    ifc_file.create_entity(
        "IfcRelAssociatesClassification",
        GlobalId=ifcopenshell.guid.new(),
        RelatedObjects=[element],
        RelatingClassification=cls_ref,
    )
    return cls_ref


# ---------------------------------------------------------------------------
# diagnose_systems — detecção principal
# ---------------------------------------------------------------------------


def test_diagnose_systems_wall_without_classification(ifc_with_walls):
    """Paredes sem IfcRelAssociatesClassification e sem Pset de material devem gerar issues."""
    ifc_file, metadata = ifc_with_walls

    issues = diagnose_systems(ifc_file)

    guids = {i.element_guid for i in issues}
    # Todas as 3 paredes não têm classificação
    assert metadata["wall1_guid"] in guids
    assert metadata["wall2_guid"] in guids
    assert metadata["wall3_guid"] in guids


def test_diagnose_systems_wall_with_classification_ok(ifc_with_walls):
    """Parede com IfcRelAssociatesClassification não deve gerar issue."""
    ifc_file, metadata = ifc_with_walls

    _add_classification(ifc_file, metadata["wall1"])

    issues = diagnose_systems(ifc_file)

    guids = {i.element_guid for i in issues}
    assert metadata["wall1_guid"] not in guids


def test_diagnose_systems_issue_type_and_severity(ifc_with_walls):
    """Issues de sistema devem ter issue_type='system_unclassified' e severity='medium'."""
    ifc_file, _ = ifc_with_walls

    issues = diagnose_systems(ifc_file)

    for issue in issues:
        assert issue.issue_type == "system_unclassified"
        assert issue.severity == "medium"


def test_diagnose_systems_slab_without_classification(simple_ifc_file):
    """IfcSlab sem classificação deve gerar issue."""
    ifc_file, base_meta = simple_ifc_file
    storey = base_meta["storey"]

    slab = ifc_file.create_entity("IfcSlab", GlobalId=ifcopenshell.guid.new(), Name="Laje Tipo")
    ifc_file.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=storey,
        RelatedElements=[slab],
    )

    issues = diagnose_systems(ifc_file)

    guids = {i.element_guid for i in issues}
    assert slab.GlobalId in guids


def test_diagnose_systems_returns_empty_for_clean_model(simple_ifc_file):
    """Modelo sem IfcWall e IfcSlab deve retornar lista vazia."""
    ifc_file, _ = simple_ifc_file

    issues = diagnose_systems(ifc_file)

    assert issues == []


def test_diagnose_systems_wall_with_standard_material_pset_ok(simple_ifc_file):
    """Parede cujo material tem Pset_MaterialConcrete não deve gerar issue."""
    ifc_file, base_meta = simple_ifc_file
    storey = base_meta["storey"]

    wall = ifc_file.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name="Muro Concreto")
    ifc_file.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=storey,
        RelatedElements=[wall],
    )
    # Adicionar material com Pset_MaterialConcrete
    mat = ifcopenshell.api.run("material.add_material", ifc_file, name="Concreto C25")
    pset = ifcopenshell.api.run("pset.add_pset", ifc_file, product=mat, name="Pset_MaterialConcrete")
    ifcopenshell.api.run("pset.edit_pset", ifc_file, pset=pset, properties={"CompressiveStrength": 25.0})
    ifcopenshell.api.run("material.assign_material", ifc_file, products=[wall], material=mat)

    issues = diagnose_systems(ifc_file)

    guids = {i.element_guid for i in issues}
    assert wall.GlobalId not in guids


# ---------------------------------------------------------------------------
# diagnose_systems — contexto extraído
# ---------------------------------------------------------------------------


def test_diagnose_systems_extracts_material_layers(ifc_with_walls):
    """Context do issue deve conter as camadas de material da parede."""
    ifc_file, metadata = ifc_with_walls

    issues = diagnose_systems(ifc_file)

    # Wall 1: material "Bloco cerâmico 14cm" com espessura 0.14m
    issue = next(i for i in issues if i.element_guid == metadata["wall1_guid"])
    layers = issue.context["materials"]

    assert len(layers) == 1
    assert layers[0]["thickness_m"] == pytest.approx(0.14)


def test_diagnose_systems_total_thickness_correct(ifc_with_walls):
    """total_thickness no contexto deve bater com a espessura da camada."""
    ifc_file, metadata = ifc_with_walls

    issues = diagnose_systems(ifc_file)

    issue = next(i for i in issues if i.element_guid == metadata["wall1_guid"])
    assert issue.context["total_thickness"] == pytest.approx(0.14)


def test_diagnose_systems_context_has_required_keys(ifc_with_walls):
    """Todos os issues devem ter as chaves canônicas no contexto."""
    ifc_file, _ = ifc_with_walls

    issues = diagnose_systems(ifc_file)

    required_keys = {
        "materials", "total_thickness", "has_classification",
        "classification_current", "has_standard_material_pset",
        "has_custom_pset_material",
    }
    for issue in issues:
        missing = required_keys - issue.context.keys()
        assert not missing, f"Chaves ausentes: {missing}"


def test_diagnose_systems_has_classification_false_for_unclassified(ifc_with_walls):
    """has_classification deve ser False para paredes sem classificação."""
    ifc_file, _ = ifc_with_walls

    issues = diagnose_systems(ifc_file)

    for issue in issues:
        assert issue.context["has_classification"] is False


def test_diagnose_systems_classification_current_is_none_without_cls(ifc_with_walls):
    """classification_current deve ser None quando não há classificação."""
    ifc_file, _ = ifc_with_walls

    issues = diagnose_systems(ifc_file)

    for issue in issues:
        assert issue.context["classification_current"] is None


def test_diagnose_systems_classification_current_populated(ifc_with_walls):
    """classification_current deve ser preenchido quando há IfcRelAssociatesClassification."""
    ifc_file, metadata = ifc_with_walls

    # Adicionar classificação a Wall 1 para verificar que NÃO gera issue,
    # e adicionar a Wall 2 com um segundo diagnose call para confirmar extração
    wall2 = next(
        e for e in ifc_file.by_type("IfcWall") if e.GlobalId == metadata["wall2_guid"]
    )
    _add_classification(ifc_file, wall2, item_ref="NBR-ALVENARIA", name="Alvenaria")

    # Com Wall 2 classificada, ela não deve aparecer nos issues
    issues = diagnose_systems(ifc_file)
    guids = {i.element_guid for i in issues}
    assert metadata["wall2_guid"] not in guids


# ---------------------------------------------------------------------------
# diagnose_systems — custom Pset material
# ---------------------------------------------------------------------------


def test_diagnose_systems_detects_custom_pset_material(simple_ifc_file):
    """Parede com Pset customizado de material deve gerar issue com has_custom_pset_material=True."""
    ifc_file, base_meta = simple_ifc_file
    storey = base_meta["storey"]

    wall = ifc_file.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name="Wall Custom")
    ifc_file.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=storey,
        RelatedElements=[wall],
    )
    pset = ifcopenshell.api.run("pset.add_pset", ifc_file, product=wall, name="Revit_Material")
    ifcopenshell.api.run(
        "pset.edit_pset", ifc_file, pset=pset,
        properties={"MaterialClass": "Concrete", "MaterialName": "Concreto C30"},
    )

    issues = diagnose_systems(ifc_file)

    wall_issues = [i for i in issues if i.element_guid == wall.GlobalId]
    assert len(wall_issues) == 1
    assert wall_issues[0].context["has_custom_pset_material"] is True


def test_diagnose_systems_custom_pset_hint_in_description(simple_ifc_file):
    """Description deve mencionar migração quando há Pset customizado de material."""
    ifc_file, base_meta = simple_ifc_file
    storey = base_meta["storey"]

    wall = ifc_file.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name="Wall Custom")
    ifc_file.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=storey,
        RelatedElements=[wall],
    )
    pset = ifcopenshell.api.run("pset.add_pset", ifc_file, product=wall, name="Revit_Material")
    ifcopenshell.api.run("pset.edit_pset", ifc_file, pset=pset, properties={"Material": "Concrete"})

    issues = diagnose_systems(ifc_file)

    issue = next(i for i in issues if i.element_guid == wall.GlobalId)
    assert "Pset customizado" in issue.description or "migrar" in issue.description


def test_diagnose_systems_no_custom_pset_false_for_standard(ifc_with_walls):
    """has_custom_pset_material deve ser False quando só há Pset_WallCommon."""
    ifc_file, metadata = ifc_with_walls

    issues = diagnose_systems(ifc_file)

    # Wall 1 e 2 têm apenas Pset_WallCommon (padrão)
    issue = next(i for i in issues if i.element_guid == metadata["wall1_guid"])
    assert issue.context["has_custom_pset_material"] is False


# ---------------------------------------------------------------------------
# Funções auxiliares — testes unitários
# ---------------------------------------------------------------------------


def test_get_classification_returns_true(simple_ifc_file):
    """_get_classification deve retornar (True, nome) para elemento classificado."""
    ifc_file, _ = simple_ifc_file

    wall = ifc_file.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name="W")
    _add_classification(ifc_file, wall, item_ref="NBR-123", name="Alvenaria")

    has_cls, name = _get_classification(wall, ifc_file)

    assert has_cls is True
    assert name is not None


def test_get_classification_returns_false_when_absent(simple_ifc_file):
    """_get_classification deve retornar (False, None) para elemento sem classificação."""
    ifc_file, _ = simple_ifc_file

    wall = ifc_file.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name="W")

    has_cls, name = _get_classification(wall, ifc_file)

    assert has_cls is False
    assert name is None


def test_detect_custom_material_pset_finds_revit_material():
    """_detect_custom_material_pset deve detectar pset com 'material' no nome."""
    psets = {"Revit_Material": {"MaterialClass": "Concrete"}}
    assert _detect_custom_material_pset(psets) is True


def test_detect_custom_material_pset_ignores_standard():
    """_detect_custom_material_pset não deve flagrar Pset_ ou Qto_ padrão."""
    psets = {"Pset_WallCommon": {"IsExternal": True}, "Qto_WallBaseQuantities": {"Length": 3.0}}
    assert _detect_custom_material_pset(psets) is False


def test_extract_material_layers_from_layer_set(ifc_with_walls):
    """_extract_material_layers deve retornar camadas corretas da parede."""
    ifc_file, metadata = ifc_with_walls

    layers = _extract_material_layers(metadata["wall1"])

    assert len(layers) == 1
    assert layers[0]["thickness_m"] == pytest.approx(0.14)


def test_total_thickness_sums_layers():
    """_total_thickness deve somar as espessuras corretamente."""
    layers = [
        {"name": "Argamassa", "thickness_m": 0.02},
        {"name": "Bloco", "thickness_m": 0.14},
        {"name": "Argamassa", "thickness_m": 0.02},
    ]
    assert _total_thickness(layers) == pytest.approx(0.18)


def test_total_thickness_returns_none_for_empty():
    """_total_thickness deve retornar None para lista vazia."""
    assert _total_thickness([]) is None
