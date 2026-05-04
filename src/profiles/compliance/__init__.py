"""Perfil de compliance normativo."""

from src.models import ReadinessProfile


def build_profile() -> ReadinessProfile:
    return ReadinessProfile(
        id="compliance_readiness",
        name="Code-compliance readiness",
        description="Verifica dados mínimos para checagens normativas e compliance downstream.",
        profile_group="compliance",
        ids_filename="compliance_readiness.ids",
        required_extractors=["thermal", "materials", "spaces", "relations", "classifications"],
        rule_pack="compliance_rules",
        prompt_pack="compliance_prompts",
        issue_types=["pset_missing", "space_unnamed", "relation_broken", "system_unclassified", "classification_missing"],
        blocking_severities=["high"],
        entity_scope=["IfcSite", "IfcBuilding", "IfcBuildingStorey", "IfcSpace", "IfcWall", "IfcSlab"],
        supported_data_categories=["entities", "properties", "psets", "materials", "classifications", "relations"],
        external_classification_systems=["bSDD", "Uniclass"],
    )
