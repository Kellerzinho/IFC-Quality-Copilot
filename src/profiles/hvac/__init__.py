"""Perfil inicial de HVAC."""

from src.models import ReadinessProfile


def build_profile() -> ReadinessProfile:
    return ReadinessProfile(
        id="hvac_readiness",
        name="HVAC-readiness",
        description="Prepara o IFC para leitura de elementos MEP e relações espaciais de HVAC.",
        profile_group="hvac",
        required_extractors=["spaces", "assets", "locations", "relations", "boundaries"],
        rule_pack="fm_rules",
        prompt_pack="fm_prompts",
        issue_types=["asset_unidentified", "location_missing", "relation_broken", "space_unnamed"],
        blocking_severities=["high", "medium"],
        entity_scope=[
            "IfcSpace",
            "IfcFlowSegment",
            "IfcFlowTerminal",
            "IfcFlowFitting",
            "IfcDistributionElement",
            "IfcRelContainedInSpatialStructure",
            "IfcRelSpaceBoundary",
        ],
        supported_data_categories=["entities", "properties", "classifications", "relations", "boundaries"],
        external_classification_systems=["bSDD"],
    )
