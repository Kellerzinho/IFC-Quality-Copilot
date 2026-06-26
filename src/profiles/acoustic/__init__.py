"""Perfil de desempenho acústico."""

from src.models import ReadinessProfile


def build_profile() -> ReadinessProfile:
    return ReadinessProfile(
        id="acoustic_readiness",
        name="Acoustic performance readiness",
        description="Verifica dados de isolamento acústico conforme ABNT NBR 15575-4/5.",
        profile_group="compliance",
        ids_filename="acoustic_readiness.ids",
        required_extractors=["thermal", "materials", "spaces", "relations"],
        rule_pack="acoustic_rules",
        prompt_pack="acoustic_prompts",
        issue_types=["pset_missing", "space_unnamed", "relation_broken"],
        blocking_severities=["high"],
        entity_scope=[
            "IfcWall",
            "IfcSlab",
            "IfcDoor",
            "IfcWindow",
            "IfcSpace",
        ],
        supported_data_categories=["entities", "properties", "psets", "relations"],
        external_classification_systems=["bSDD"],
    )
