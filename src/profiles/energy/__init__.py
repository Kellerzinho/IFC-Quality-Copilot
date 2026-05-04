"""Perfil de energia/envoltória."""

from src.models import ReadinessProfile


def build_profile() -> ReadinessProfile:
    return ReadinessProfile(
        id="energy_readiness",
        name="Energy-readiness",
        description="Verifica dados térmicos e de envoltória para simulação energética.",
        profile_group="energy",
        ids_filename="energy_readiness.ids",
        required_extractors=["thermal", "materials", "spaces", "external_elements", "boundaries"],
        rule_pack="energy_rules",
        prompt_pack="energy_prompts",
        issue_types=["pset_missing", "space_unnamed", "relation_broken", "thermal_incomplete"],
        blocking_severities=["high"],
        entity_scope=["IfcSpace", "IfcWall", "IfcSlab", "IfcRelSpaceBoundary"],
        supported_data_categories=["entities", "properties", "psets", "materials", "relations", "boundaries"],
    )
