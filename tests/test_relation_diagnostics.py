"""Testes para o módulo de diagnóstico de relações espaciais."""

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.guid
import pytest

from src.ifc_analyzer.relation_diagnostics import (
    diagnose_relations,
    _build_fills_set,
    _build_contained_set,
    _check_space_boundary_coverage,
)


# ---------------------------------------------------------------------------
# Helpers de asserção
# ---------------------------------------------------------------------------


def _fills_issues(issues, guid):
    """Filtra issues de IfcRelFillsElement ausente para um GUID específico."""
    return [
        i for i in issues
        if i.element_guid == guid
        and i.context["expected_relation"] == "IfcRelFillsElement"
    ]


def _orphan_issues(issues, guid):
    """Filtra issues de elemento órfão para um GUID específico."""
    return [
        i for i in issues
        if i.element_guid == guid
        and i.context["expected_relation"] == "IfcRelContainedInSpatialStructure"
    ]


def _coverage_issues(issues):
    """Filtra issues de baixa cobertura de IfcRelSpaceBoundary."""
    return [
        i for i in issues
        if i.context.get("expected_relation") == "IfcRelSpaceBoundary"
    ]


# ---------------------------------------------------------------------------
# Check 1 — IfcRelFillsElement
# ---------------------------------------------------------------------------


def test_diagnose_relations_detects_door_without_fills(ifc_with_doors):
    """Door 2 (sem IfcRelFillsElement) deve gerar issue de relation_broken."""
    ifc_file, metadata = ifc_with_doors

    issues = diagnose_relations(ifc_file)

    fills = _fills_issues(issues, metadata["door2_guid"])
    assert len(fills) == 1
    assert fills[0].issue_type == "relation_broken"
    assert fills[0].severity == "high"


def test_diagnose_relations_ignores_door_with_fills(ifc_with_doors):
    """Door 1 (com IfcRelFillsElement) não deve gerar issue de fills."""
    ifc_file, metadata = ifc_with_doors

    issues = diagnose_relations(ifc_file)

    fills = _fills_issues(issues, metadata["door1_guid"])
    assert len(fills) == 0


def test_diagnose_relations_fills_issue_fields(ifc_with_doors):
    """Issue de IfcRelFillsElement ausente deve ter campos corretos."""
    ifc_file, metadata = ifc_with_doors

    issues = diagnose_relations(ifc_file)

    issue = _fills_issues(issues, metadata["door2_guid"])[0]
    assert issue.element_class == "IfcDoor"
    assert issue.element_guid == metadata["door2_guid"]
    assert "IfcRelFillsElement" in issue.description
    assert issue.context["expected_relation"] == "IfcRelFillsElement"
    assert issue.context["wall_host_guid"] is None


def test_diagnose_relations_window_without_fills(simple_ifc_file):
    """IfcWindow sem IfcRelFillsElement também deve gerar issue."""
    ifc_file, base_meta = simple_ifc_file
    storey = base_meta["storey"]

    window = ifc_file.create_entity(
        "IfcWindow", GlobalId=ifcopenshell.guid.new(), Name="Window 1"
    )
    ifc_file.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=storey,
        RelatedElements=[window],
    )

    issues = diagnose_relations(ifc_file)

    fills = _fills_issues(issues, window.GlobalId)
    assert len(fills) == 1
    assert fills[0].element_class == "IfcWindow"


def test_diagnose_relations_nearby_spaces_populated(ifc_with_doors):
    """Issue de Door 2 deve conter nearby_spaces do storey."""
    ifc_file, metadata = ifc_with_doors
    storey = metadata["storey"]

    # Adicionar um espaço ao storey para verificar nearby_spaces
    space = ifc_file.create_entity(
        "IfcSpace", GlobalId=ifcopenshell.guid.new(), Name="Sala"
    )
    ifc_file.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=storey,
        RelatedElements=[space],
    )

    issues = diagnose_relations(ifc_file)
    issue = _fills_issues(issues, metadata["door2_guid"])[0]

    nearby_guids = {s["guid"] for s in issue.context["nearby_spaces"]}
    assert space.GlobalId in nearby_guids


# ---------------------------------------------------------------------------
# Check 2 — Elementos órfãos
# ---------------------------------------------------------------------------


def test_diagnose_relations_detects_orphan_element(simple_ifc_file):
    """IfcFurnishingElement sem IfcRelContainedInSpatialStructure deve gerar issue."""
    ifc_file, _ = simple_ifc_file

    # Criar elemento sem nenhuma relação de contenção
    sofa = ifc_file.create_entity(
        "IfcFurnishingElement", GlobalId=ifcopenshell.guid.new(), Name="Sofá"
    )

    issues = diagnose_relations(ifc_file)

    orphans = _orphan_issues(issues, sofa.GlobalId)
    assert len(orphans) == 1
    assert orphans[0].severity == "medium"
    assert orphans[0].issue_type == "relation_broken"


def test_diagnose_relations_orphan_issue_fields(simple_ifc_file):
    """Issue de elemento órfão deve ter campos esperados."""
    ifc_file, _ = simple_ifc_file

    elem = ifc_file.create_entity(
        "IfcFlowTerminal", GlobalId=ifcopenshell.guid.new(), Name="Equip 1"
    )

    issues = diagnose_relations(ifc_file)

    issue = _orphan_issues(issues, elem.GlobalId)[0]
    assert issue.element_class == "IfcFlowTerminal"
    assert issue.context["expected_relation"] == "IfcRelContainedInSpatialStructure"
    assert "IfcRelContainedInSpatialStructure" in issue.description


def test_diagnose_relations_contained_element_not_orphan(ifc_with_doors):
    """Elementos contidos em storey não devem gerar issue de elemento órfão."""
    ifc_file, metadata = ifc_with_doors

    issues = diagnose_relations(ifc_file)

    # Door 1 está no storey → não é órfão
    orphans = _orphan_issues(issues, metadata["door1_guid"])
    assert len(orphans) == 0


def test_diagnose_relations_orphan_door_also_has_fills_issue(simple_ifc_file):
    """Porta completamente desconectada (sem fills e sem contenção) gera ambos os issues."""
    ifc_file, _ = simple_ifc_file

    door = ifc_file.create_entity(
        "IfcDoor", GlobalId=ifcopenshell.guid.new(), Name="Floating Door"
    )

    issues = diagnose_relations(ifc_file)

    fills = _fills_issues(issues, door.GlobalId)
    orphans = _orphan_issues(issues, door.GlobalId)
    assert len(fills) == 1
    assert len(orphans) == 1


# ---------------------------------------------------------------------------
# Check 3 — Cobertura de IfcRelSpaceBoundary
# ---------------------------------------------------------------------------


def test_diagnose_relations_low_space_boundary_coverage(ifc_with_doors):
    """Modelo sem IfcRelSpaceBoundary deve gerar issue de baixa cobertura."""
    ifc_file, _ = ifc_with_doors

    issues = diagnose_relations(ifc_file)

    coverage = _coverage_issues(issues)
    assert len(coverage) == 1
    assert coverage[0].issue_type == "relation_broken"
    assert coverage[0].severity == "low"


def test_diagnose_relations_coverage_issue_context(ifc_with_doors):
    """Issue de cobertura deve ter campos coverage_pct, total_elements e elements_with_boundary."""
    ifc_file, _ = ifc_with_doors

    issues = diagnose_relations(ifc_file)

    issue = _coverage_issues(issues)[0]
    ctx = issue.context
    assert "coverage_pct" in ctx
    assert "total_elements" in ctx
    assert "elements_with_boundary" in ctx
    assert ctx["coverage_pct"] == 0
    assert ctx["total_elements"] > 0


def test_diagnose_relations_no_coverage_issue_when_above_threshold(
    ifc_with_boundary_adjacency,
):
    """Modelo com ≥10% de cobertura não deve gerar issue de baixa cobertura."""
    ifc_file, metadata = ifc_with_boundary_adjacency
    # ifc_with_boundary_adjacency tem 2 paredes e 2 space boundaries
    # shared_wall + ext_wall = 2 elementos totais, 2 com boundary = 100% ≥ 10%

    issues = diagnose_relations(ifc_file)

    coverage = _coverage_issues(issues)
    assert len(coverage) == 0


def test_diagnose_relations_coverage_issue_is_one_per_model(simple_ifc_file):
    """Mesmo com múltiplos elementos sem boundary, deve haver apenas 1 issue de cobertura."""
    ifc_file, base_meta = simple_ifc_file
    storey = base_meta["storey"]

    for i in range(5):
        wall = ifc_file.create_entity(
            "IfcWall", GlobalId=ifcopenshell.guid.new(), Name=f"Wall {i}"
        )
        ifc_file.create_entity(
            "IfcRelContainedInSpatialStructure",
            GlobalId=ifcopenshell.guid.new(),
            RelatingStructure=storey,
            RelatedElements=[wall],
        )

    issues = diagnose_relations(ifc_file)

    coverage = _coverage_issues(issues)
    assert len(coverage) == 1


def test_diagnose_relations_empty_model_no_coverage_issue(simple_ifc_file):
    """Modelo sem IfcWall/Door/Window não deve gerar issue de cobertura."""
    ifc_file, _ = simple_ifc_file

    issues = diagnose_relations(ifc_file)

    coverage = _coverage_issues(issues)
    assert len(coverage) == 0


# ---------------------------------------------------------------------------
# Índices internos — testes unitários
# ---------------------------------------------------------------------------


def test_build_fills_set(ifc_with_doors):
    """_build_fills_set deve conter guid de Door 1 mas não de Door 2."""
    ifc_file, metadata = ifc_with_doors

    fills = _build_fills_set(ifc_file)

    assert metadata["door1_guid"] in fills
    assert metadata["door2_guid"] not in fills


def test_build_contained_set(ifc_with_doors):
    """_build_contained_set deve conter os GUIDs das portas contidas no storey."""
    ifc_file, metadata = ifc_with_doors

    contained = _build_contained_set(ifc_file)

    assert metadata["door1_guid"] in contained
    assert metadata["door2_guid"] in contained
