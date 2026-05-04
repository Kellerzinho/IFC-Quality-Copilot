"""Perfil base para leitura ampla de dados IFC."""

from src.models import ReadinessProfile


def build_profile() -> ReadinessProfile:
    return ReadinessProfile(
        id="base_ifc",
        name="Base IFC",
        description="Perfil base para leitura e consistência estrutural de entidades e relações IFC.",
        profile_group="base_ifc",
        required_extractors=["spaces", "relations", "quantities", "materials"],
        issue_types=["pset_missing", "relation_broken", "quantity_missing", "classification_missing"],
        blocking_severities=["high"],
        entity_scope=[
            "IfcSite",
            "IfcBuilding",
            "IfcBuildingStorey",
            "IfcSpace",
            "IfcWall",
            "IfcSlab",
            "IfcRelContainedInSpatialStructure",
            "IfcRelSpaceBoundary",
            "IfcElementQuantity",
        ],
        supported_data_categories=[
            "entities",
            "properties",
            "psets",
            "quantities",
            "materials",
            "relations",
            "boundaries",
        ],
    )
