"""Testes para o registry central de entidades e categorias IFC."""

from src.ifc_registry import DEFAULT_IFC_DATA_REGISTRY


def test_registry_resolves_entities_and_aliases():
    wall = DEFAULT_IFC_DATA_REGISTRY.entity("IFCWALL")

    assert wall is not None
    assert wall.name == "IfcWall"
    assert "envelope" in wall.categories


def test_registry_includes_spatial_and_mep_entities():
    assert DEFAULT_IFC_DATA_REGISTRY.has_entity("IfcSite")
    assert DEFAULT_IFC_DATA_REGISTRY.has_entity("IfcBuildingStorey")
    assert DEFAULT_IFC_DATA_REGISTRY.has_entity("IfcFlowTerminal")


def test_registry_exposes_resources_for_space_and_boundaries():
    assert "Pset_SpaceCommon" in DEFAULT_IFC_DATA_REGISTRY.resources_for_entity("IfcSpace", "psets")
    assert "NetFloorArea" in DEFAULT_IFC_DATA_REGISTRY.resources_for_entity("IfcSpace", "quantities")
    assert "external" in DEFAULT_IFC_DATA_REGISTRY.resources_for_entity("IfcRelSpaceBoundary", "boundaries")
