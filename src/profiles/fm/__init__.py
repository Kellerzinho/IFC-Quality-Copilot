"""Perfil de facilities management."""

from src.models import ReadinessProfile


def build_profile() -> ReadinessProfile:
    return ReadinessProfile(
        id="fm_readiness",
        name="Facility Management-readiness",
        description="Verifica se o modelo suporta operação, manutenção e localização de ativos.",
        profile_group="fm",
        ids_filename="fm_readiness.ids",
        required_extractors=["spaces", "assets", "locations", "relations"],
        rule_pack="fm_rules",
        prompt_pack="fm_prompts",
        issue_types=["space_unnamed", "asset_unidentified", "location_missing", "relation_broken"],
        blocking_severities=["high", "medium"],
        entity_scope=["IfcSite", "IfcBuilding", "IfcBuildingStorey", "IfcSpace", "IfcDistributionElement"],
        supported_data_categories=["entities", "properties", "classifications", "relations"],
        external_classification_systems=["Uniclass", "OmniClass", "bSDD"],
    )
