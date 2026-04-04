"""Registro de perfis de readiness e carregamento de perfis customizados via IDS."""

from pathlib import Path

from src.models import ProfileRegistry, ReadinessProfile
from src.translator.ids_parser import parse_ids

# ---------------------------------------------------------------------------
# Lookup tables para inferência de issue_types e extractors
# ---------------------------------------------------------------------------

_ENTITY_TO_EXTRACTORS: dict[str, list[str]] = {
    "IFCWALL": ["quantities", "materials"],
    "IFCSLAB": ["quantities", "materials"],
    "IFCSPACE": ["spaces"],
    "IFCDOOR": ["quantities"],
    "IFCWINDOW": ["quantities"],
}

_THERMAL_PROPS: set[str] = {"ThermalTransmittance", "ThermalConductivity", "HeatCapacity"}

_SPACE_NAME_PROPS: set[str] = {"LongName", "Name"}


def _infer_issue_type(req: dict[str, str]) -> str:
    """Infere o issue_type a partir de um requirement de IDSSpecification."""
    pset = req.get("pset", "")
    prop = req.get("prop", "")
    if pset == "IFC_RELATION":
        return "relation_broken"
    if pset == "" and prop in _SPACE_NAME_PROPS:
        return "space_unnamed"
    return "pset_missing"


def _infer_extractors(entity: str, requirements: list[dict[str, str]]) -> list[str]:
    """Infere os extractors necessários a partir da entidade e dos requirements."""
    extractors: list[str] = list(_ENTITY_TO_EXTRACTORS.get(entity, []))
    for req in requirements:
        if req.get("prop") in _THERMAL_PROPS and "thermal" not in extractors:
            extractors.append("thermal")
        if req.get("pset") == "IFC_RELATION" and "relations" not in extractors:
            extractors.append("relations")
    return extractors


# ---------------------------------------------------------------------------
# Perfis padrão
# ---------------------------------------------------------------------------

def create_default_registry() -> ProfileRegistry:
    """Cria registro com os 4 perfis padrão do sistema."""
    registry = ProfileRegistry()

    registry.register(ReadinessProfile(
        id="budget_readiness",
        name="Orçamento-readiness",
        description="Verifica se o modelo possui informação mínima para levantamento quantitativo e vinculação orçamentária.",
        ids_filename="budget_readiness.ids",
        required_extractors=["quantities", "materials", "classifications"],
        rule_pack="budget_rules",
        prompt_pack="budget_prompts",
        issue_types=["pset_missing", "system_unclassified", "quantity_missing", "classification_missing"],
        blocking_severities=["high"],
    ))

    registry.register(ReadinessProfile(
        id="energy_readiness",
        name="Energy/HVAC-readiness",
        description="Verifica se o IFC está apto para simulação energética e verificações de envoltória.",
        ids_filename="energy_readiness.ids",
        required_extractors=["thermal", "materials", "spaces", "external_elements"],
        rule_pack="energy_rules",
        prompt_pack="energy_prompts",
        issue_types=["pset_missing", "space_unnamed", "relation_broken"],
        blocking_severities=["high"],
    ))

    registry.register(ReadinessProfile(
        id="fm_readiness",
        name="Facility Management-readiness",
        description="Verifica se o modelo pode sustentar operação e manutenção do edifício.",
        ids_filename="fm_readiness.ids",
        required_extractors=["spaces", "assets", "locations"],
        rule_pack="fm_rules",
        prompt_pack="fm_prompts",
        issue_types=["space_unnamed", "asset_unidentified", "location_missing"],
        blocking_severities=["high", "medium"],
    ))

    registry.register(ReadinessProfile(
        id="compliance_readiness",
        name="Code-compliance readiness",
        description="Verifica se o IFC contém os dados mínimos para checagem normativa posterior (NBR 15575).",
        ids_filename="compliance_readiness.ids",
        required_extractors=["thermal", "materials", "spaces", "relations"],
        rule_pack="compliance_rules",
        prompt_pack="compliance_prompts",
        issue_types=["pset_missing", "space_unnamed", "relation_broken", "system_unclassified"],
        blocking_severities=["high"],
    ))

    return registry


# ---------------------------------------------------------------------------
# Carregamento de perfil customizado via IDS
# ---------------------------------------------------------------------------

def load_custom_profile_from_ids(ids_path: str, profile_name: str | None = None) -> ReadinessProfile:
    """Cria um ReadinessProfile a partir de um arquivo IDS uploadado pelo usuário.

    Parseia o IDS para extrair specs, infere issue_types e extractors necessários
    a partir das specs usando lookup tables, e gera um profile_id baseado no filename.
    Se profile_name não fornecido, usa o filename sem extensão.
    """
    specs = parse_ids(ids_path)
    stem = Path(ids_path).stem

    issue_types: list[str] = []
    required_extractors: list[str] = []

    for spec in specs:
        for ext in _infer_extractors(spec.applicability_entity, spec.requirements):
            if ext not in required_extractors:
                required_extractors.append(ext)
        for req in spec.requirements:
            issue_type = _infer_issue_type(req)
            if issue_type not in issue_types:
                issue_types.append(issue_type)

    return ReadinessProfile(
        id=stem,
        name=profile_name or stem,
        description=f"Perfil gerado a partir de {Path(ids_path).name}.",
        ids_filename=None,
        required_extractors=required_extractors,
        issue_types=issue_types,
        blocking_severities=["high"],
    )
