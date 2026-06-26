"""Perfil de segurança contra incêndio."""

from src.models import ReadinessProfile


def build_profile() -> ReadinessProfile:
    return ReadinessProfile(
        id="fire_safety_readiness",
        name="Fire safety readiness",
        description="Verifica dados de resistência ao fogo conforme NBR 14432 e Instruções Técnicas do CBPMESP.",
        profile_group="compliance",
        ids_filename="fire_safety_readiness.ids",
        required_extractors=["thermal", "materials", "relations"],
        rule_pack="fire_safety_rules",
        prompt_pack="fire_safety_prompts",
        issue_types=["pset_missing", "relation_broken"],
        blocking_severities=["high"],
        entity_scope=[
            "IfcWall",
            "IfcSlab",
            "IfcDoor",
            "IfcBeam",
            "IfcColumn",
            "IfcStair",
            "IfcRoof",
        ],
        supported_data_categories=["entities", "properties", "psets", "relations"],
        external_classification_systems=["bSDD"],
    )
