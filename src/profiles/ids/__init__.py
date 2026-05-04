"""Perfil genérico para execução de múltiplos IDS."""

from src.models import ReadinessProfile


def build_profile() -> ReadinessProfile:
    return ReadinessProfile(
        id="ids_generic",
        name="IDS Generic",
        description="Perfil genérico para tradução e execução de múltiplas specifications IDS.",
        profile_group="ids",
        required_extractors=["spaces", "relations", "quantities", "materials", "classifications"],
        issue_types=["pset_missing", "relation_broken", "quantity_missing", "classification_missing"],
        blocking_severities=["high"],
        supported_data_categories=["properties", "psets", "quantities", "classifications", "relations"],
    )
