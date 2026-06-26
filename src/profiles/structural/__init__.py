"""Perfil de prontidão estrutural."""

from src.models import ReadinessProfile


def build_profile() -> ReadinessProfile:
    return ReadinessProfile(
        id="structural_readiness",
        name="Structural analysis readiness",
        description="Verifica dados estruturais para intercâmbio com software de análise (SAP2000, ETABS, Robot). Cobre NBR 6118 e NBR 7190.",
        profile_group="engineering",
        ids_filename="structural_readiness.ids",
        required_extractors=["thermal", "materials", "quantities", "relations"],
        rule_pack="structural_rules",
        prompt_pack="structural_prompts",
        issue_types=[
            "pset_missing",
            "system_unclassified",
            "quantity_missing",
            "relation_broken",
        ],
        blocking_severities=["high"],
        entity_scope=[
            "IfcWall",
            "IfcSlab",
            "IfcBeam",
            "IfcColumn",
            "IfcStair",
            "IfcRoof",
        ],
        supported_data_categories=["entities", "properties", "psets", "quantities", "relations"],
        external_classification_systems=["bSDD"],
    )
