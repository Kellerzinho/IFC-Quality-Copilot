"""Registro de perfis de readiness e carregamento de perfis customizados via IDS."""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from src.ifc_registry import DEFAULT_IFC_DATA_REGISTRY
from src.models import ProfileRegistry, ReadinessProfile
from src.profiles.base_ifc import build_profile as build_base_ifc_profile
from src.profiles.budget import build_profile as build_budget_profile
from src.profiles.compliance import build_profile as build_compliance_profile
from src.profiles.energy import build_profile as build_energy_profile
from src.profiles.fm import build_profile as build_fm_profile
from src.profiles.hvac import build_profile as build_hvac_profile
from src.profiles.ids import build_profile as build_ids_profile
from src.translator.ids_parser import parse_ids

_PROPERTY_TO_EXTRACTORS: dict[str, list[str]] = {
    "ThermalTransmittance": ["thermal"],
    "ThermalConductivity": ["thermal"],
    "HeatCapacity": ["thermal"],
    "LongName": ["spaces"],
    "Name": ["spaces"],
    "NetFloorArea": ["quantities"],
    "GrossFloorArea": ["quantities"],
    "NetSideArea": ["quantities"],
    "NetArea": ["quantities"],
    "Volume": ["quantities"],
}

_FACET_TO_ISSUE_TYPE: dict[str, str] = {
    "classification": "classification_missing",
    "material": "material_unmapped",
    "quantity": "quantity_missing",
    "relation": "relation_broken",
}


def _infer_issue_type(req: dict[str, str], entity: str) -> str:
    facet_type = req.get("facet_type", "")
    if facet_type in _FACET_TO_ISSUE_TYPE:
        return _FACET_TO_ISSUE_TYPE[facet_type]

    pset = req.get("pset", "")
    prop = req.get("prop", "")
    if pset == "IFC_RELATION":
        return "relation_broken"
    if entity == "IfcSpace" and prop in {"LongName", "Name"}:
        return "space_unnamed"
    return "pset_missing"


def _infer_extractors(entity: str, requirements: list[dict[str, str]]) -> list[str]:
    extractors: list[str] = []
    definition = DEFAULT_IFC_DATA_REGISTRY.entity(entity)
    if definition is None:
        logger.warning("Entidade IFC desconhecida na inferência de extractors: '{}'", entity)
    else:
        if "spatial" in definition.categories or entity == "IfcSpace":
            extractors.append("spaces")
        if "boundary" in definition.categories:
            extractors.append("boundaries")
        if "relation" in definition.categories:
            extractors.append("relations")
        if any(name.startswith("Qto_") for name in definition.default_quantities):
            extractors.append("quantities")
        if any(name.startswith("Pset_") for name in definition.default_psets):
            extractors.append("materials")

    for req in requirements:
        facet_type = req.get("facet_type", "")
        if facet_type == "classification" and "classifications" not in extractors:
            extractors.append("classifications")
        if facet_type == "material" and "materials" not in extractors:
            extractors.append("materials")
        if facet_type == "quantity" and "quantities" not in extractors:
            extractors.append("quantities")
        if facet_type == "relation":
            if "relations" not in extractors:
                extractors.append("relations")
            if req.get("prop") == "IFCRELSPACEBOUNDARY" and "boundaries" not in extractors:
                extractors.append("boundaries")

        for extractor in _PROPERTY_TO_EXTRACTORS.get(req.get("prop", ""), []):
            if extractor not in extractors:
                extractors.append(extractor)

    return extractors


def _infer_entity_scope(specs: list) -> list[str]:
    scope: list[str] = []
    for spec in specs:
        entity = spec.applicability_entity
        canonical = DEFAULT_IFC_DATA_REGISTRY.entity(entity)
        resolved = canonical.name if canonical is not None else entity
        if resolved not in scope:
            scope.append(resolved)
    return scope


def create_default_registry() -> ProfileRegistry:
    """Cria registro com os perfis padrão suportados pelo sistema."""
    registry = ProfileRegistry()
    for profile in [
        build_base_ifc_profile(),
        build_ids_profile(),
        build_budget_profile(),
        build_energy_profile(),
        build_hvac_profile(),
        build_fm_profile(),
        build_compliance_profile(),
    ]:
        registry.register(profile)
    return registry


def load_custom_profile_from_ids(ids_path: str, profile_name: str | None = None) -> ReadinessProfile:
    """Cria um ReadinessProfile a partir de um arquivo IDS uploadado pelo usuário."""
    specs = parse_ids(ids_path)
    stem = Path(ids_path).stem

    issue_types: list[str] = []
    required_extractors: list[str] = []
    supported_data_categories: list[str] = []

    for spec in specs:
        entity = DEFAULT_IFC_DATA_REGISTRY.entity(spec.applicability_entity)
        resolved_entity = entity.name if entity is not None else spec.applicability_entity
        for ext in _infer_extractors(resolved_entity, spec.requirements):
            if ext not in required_extractors:
                required_extractors.append(ext)
        for req in spec.requirements:
            issue_type = _infer_issue_type(req, resolved_entity)
            if issue_type not in issue_types:
                issue_types.append(issue_type)
            facet_type = req.get("facet_type", "property") or "property"
            if facet_type not in supported_data_categories:
                supported_data_categories.append(facet_type)

    return ReadinessProfile(
        id=stem,
        name=profile_name or stem,
        description=f"Perfil gerado a partir de {Path(ids_path).name}.",
        profile_group="ids",
        ids_filename=None,
        ids_sources=[Path(ids_path).name],
        required_extractors=required_extractors,
        issue_types=issue_types,
        blocking_severities=["high"],
        entity_scope=_infer_entity_scope(specs),
        supported_data_categories=supported_data_categories,
    )
