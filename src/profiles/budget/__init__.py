"""Perfil de orçamento/readiness quantitativo."""

from src.models import ReadinessProfile


def build_profile() -> ReadinessProfile:
    return ReadinessProfile(
        id="budget_readiness",
        name="Orçamento-readiness",
        description="Verifica informação mínima para quantificação, materiais e classificação de orçamento.",
        profile_group="budget",
        ids_filename="budget_readiness.ids",
        required_extractors=["quantities", "materials", "classifications"],
        rule_pack="budget_rules",
        prompt_pack="budget_prompts",
        issue_types=["pset_missing", "system_unclassified", "quantity_missing", "classification_missing"],
        blocking_severities=["high"],
        entity_scope=["IfcWall", "IfcSlab", "IfcBuildingStorey", "IfcElementQuantity"],
        supported_data_categories=["entities", "quantities", "materials", "classifications", "psets"],
        external_classification_systems=["Uniclass", "OmniClass"],
    )
