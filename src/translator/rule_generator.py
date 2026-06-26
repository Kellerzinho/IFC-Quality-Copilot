"""Gerador de OperationalRules a partir de IDSSpecifications."""

import math
import re
from typing import Any, Literal

import ifcopenshell
import ifcopenshell.util.element
from loguru import logger

from src.ifc_registry import DEFAULT_IFC_DATA_REGISTRY
from src.models import IDSSpecification, Issue, OperationalRule, ReadinessProfile
from src.translator.pset_resolver import resolve_property

# Propriedades com tipo conhecido para inferência de check_type
_NUMERIC_PROPS: frozenset[str] = frozenset({
    "ThermalTransmittance",
    "CompressiveStrength",
    "NetFloorArea",
    "GrossFloorArea",
    "Area",
    "Volume",
    "Height",
    "Width",
    "Thickness",
    "SpanRatio",
    "ReinforcementRatio",
    "SoundTransmissionLoss",
    "AcousticRating",
})

_BOOLEAN_PROPS: frozenset[str] = frozenset({
    "IsExternal",
    "LoadBearing",
    "IsLoadBearing",
    "FireResistance",
    "Combustible",
    "Accessible",
    "IsAccessible",
    "IsStructural",
})

# Propriedades que disparam severidade high
_HIGH_SEVERITY_PROPS: frozenset[str] = frozenset({
    "ThermalTransmittance",
    "CompressiveStrength",
    "SoundTransmissionLoss",
})

# Propriedades que disparam severidade medium
_MEDIUM_SEVERITY_PROPS: frozenset[str] = frozenset({
    "IsExternal",
    "LoadBearing",
    "IsLoadBearing",
    "FireRating",
    "FireResistance",
    "AcousticRating",
})

# Convenção interna do ids_parser para atributos e relações
_PSET_ATTRIBUTE = ""
_PSET_RELATION = "IFC_RELATION"

# Propriedades resolvíveis por tabela de referência normativa
_LOOKUP_PROPS: frozenset[str] = frozenset({
    "ThermalTransmittance",
    "Absorptance",
    "SHGC",
    "SolarHeatGainCoefficient",
    "ThermalConductivity",
})

# Propriedades de nome de espaço que disparam estratégia LLM
_SPACE_ATTR_PROPS: frozenset[str] = frozenset({"LongName", "Name"})

# Propriedades que requerem contexto térmico completo
_THERMAL_CONTEXT_PROPS: frozenset[str] = frozenset({
    "ThermalTransmittance",
    "Absorptance",
    "SHGC",
})


# Lookup para classes IFC com nomes compostos que capitalize() distorce
def _to_ifc_class(entity: str) -> str:
    """Converte nome de entidade IDS uppercase para nome de classe IfcOpenShell.

    Exemplos:
        "IFCWALL" → "IfcWall"
        "IFCBUILDINGSTOREY" → "IfcBuildingStorey"
        "IFCWALLSTANDARDCASE" → "IfcWallStandardCase"
    """
    definition = DEFAULT_IFC_DATA_REGISTRY.entity(entity)
    if definition is not None:
        return definition.name
    key = entity.upper()
    if not key.startswith("IFC"):
        return entity
    # Fallback para classes não mapeadas: capitalize apenas (pode estar errado para compostos)
    suffix = entity[3:].capitalize()
    logger.warning("Classe IFC não mapeada '{}', usando fallback '{}'", entity, f"Ifc{suffix}")
    return f"Ifc{suffix}"


def _infer_check_type(req: dict[str, str]) -> Literal["exists", "is_numeric", "is_boolean", "equals", "not_empty"]:
    """Infere o check_type a partir do constraint e do nome da propriedade.

    Prioridade:
        1. Convenções especiais de pset (atributo direto, relação)
        2. constraint explícito do IDS
        3. Nome da propriedade para constraint "exists"
    """
    pset = req.get("pset", "")
    prop = req.get("prop", "")
    constraint = req.get("constraint", "exists")

    # Atributos diretos (LongName, Name, etc.) → not_empty por padrão
    if pset == _PSET_ATTRIBUTE:
        return "not_empty"

    # Relações IFC → exists
    if pset == _PSET_RELATION:
        return "exists"

    # Constraint explícito do IDS
    if constraint == "not_empty":
        return "not_empty"

    if constraint in ("minInclusive", "minExclusive", "maxInclusive", "maxExclusive",
                      "fractionDigits", "totalDigits", "minLength"):
        return "is_numeric"

    if constraint == "pattern":
        return "not_empty"

    if constraint.startswith("equals:"):
        value = constraint[len("equals:"):]
        if value.upper() in ("TRUE", "FALSE"):
            return "is_boolean"
        return "equals"

    # constraint == "exists" → inferir pelo nome da propriedade
    if prop in _BOOLEAN_PROPS:
        return "is_boolean"

    if prop in _NUMERIC_PROPS:
        return "is_numeric"

    return "exists"


def _infer_issue_type(req: dict[str, str], filter_entity: str) -> str:
    """Infere o issue_type baseado no contexto do requisito."""
    facet_type = req.get("facet_type", "")
    pset = req.get("pset", "")

    if facet_type == "classification":
        return "classification_missing"
    if facet_type == "material":
        return "material_unmapped"
    if facet_type == "quantity":
        return "quantity_missing"
    if pset == _PSET_RELATION:
        return "relation_broken"

    if pset == _PSET_ATTRIBUTE and filter_entity == "IfcSpace":
        return "space_unnamed"

    return "pset_missing"


def _infer_severity(req: dict[str, str]) -> Literal["high", "medium", "low"]:
    """Infere a severidade baseada no nome da propriedade e contexto do requisito."""
    pset = req.get("pset", "")
    prop = req.get("prop", "")

    if pset == _PSET_RELATION:
        return "high"

    if prop in _HIGH_SEVERITY_PROPS:
        return "high"

    if prop in _MEDIUM_SEVERITY_PROPS:
        return "medium"

    return "low"


def _build_filter_conditions(
    applicability_filters: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Converte applicability_filters em filter_conditions com operator."""
    conditions = []
    for filt in applicability_filters:
        value = filt.get("value", "")
        operator = "==" if value else "EXISTS"
        conditions.append({
            "pset": filt["pset"],
            "prop": filt["prop"],
            "operator": operator,
            "value": value,
        })
    return conditions


def _infer_suggestion_strategy(spec: IDSSpecification, req: dict[str, str]) -> str:
    """Infere suggestion_strategy a partir do tipo de check e do contexto do requisito.

    Regras de inferência (em ordem de prioridade):
        - Propriedades térmicas/solares conhecidas → "lookup_table"
        - Pset de BaseQuantities (Qto_*) → "geometric_calc"
        - Atributo de nome em IfcSpace → "llm_inference"
        - Pset de classificação IFC → "llm_inference"
        - Pset/prop de material → "copy_from_source"
        - Demais → "llm_inference"
    """
    pset = req.get("pset", "")
    prop = req.get("prop", "")
    facet_type = req.get("facet_type", "")

    if prop in _LOOKUP_PROPS:
        return "lookup_table"

    if facet_type == "classification":
        return "copy_from_source"

    if pset.startswith("Qto_"):
        return "geometric_calc"

    if pset == _PSET_ATTRIBUTE and prop in _SPACE_ATTR_PROPS:
        return "llm_inference"

    if "classification" in pset.lower():
        return "llm_inference"

    if "material" in pset.lower() or "material" in prop.lower():
        return "copy_from_source"

    return "llm_inference"


def _infer_write_action(spec: IDSSpecification, req: dict[str, str]) -> str:
    """Infere write_action a partir do issue_type e do contexto do requisito.

    Regras de inferência (em ordem de prioridade):
        - Pset de BaseQuantities (Qto_*) → "preencher_base_quantities"
        - Atributo de nome em IfcSpace → "renomear_espaco"
        - Pset de classificação → "mapear_classificacao"
        - Relação IFC → "criar_relacao_fills"
        - Demais psets → "preencher_pset"
    """
    pset = req.get("pset", "")
    prop = req.get("prop", "")
    facet_type = req.get("facet_type", "")

    if pset.startswith("Qto_"):
        return "preencher_base_quantities"

    if facet_type == "classification":
        return "mapear_classificacao"

    if pset == _PSET_ATTRIBUTE and prop in _SPACE_ATTR_PROPS:
        return "renomear_espaco"

    if "classification" in pset.lower():
        return "mapear_classificacao"

    if pset == _PSET_RELATION:
        return "criar_relacao_fills"

    return "preencher_pset"


def _infer_required_context(spec: IDSSpecification, req: dict[str, str]) -> list[str]:
    """Infere required_context baseado em padrões semânticos da propriedade e do Pset.

    Usa correspondência por keywords no nome da propriedade e do Pset para funcionar
    com qualquer IDS customizado, não apenas propriedades canônicas conhecidas.
    Garante contexto mínimo (material) para qualquer propriedade desconhecida.
    """
    pset = req.get("pset", "")
    prop = req.get("prop", "")
    facet_type = req.get("facet_type", "")
    prop_lower = prop.lower()
    pset_lower = pset.lower()

    # ---- Contexto de espaço funcional ------------------------------------
    if pset == _PSET_ATTRIBUTE and prop in _SPACE_ATTR_PROPS:
        return ["area", "contained_elements", "adjacent_spaces"]

    # ---- Relações IFC ---------------------------------------------------
    if pset == _PSET_RELATION and prop == "IFCRELSPACEBOUNDARY":
        return ["spaces", "boundaries"]

    # ---- Classificação --------------------------------------------------
    if facet_type == "classification" or "classification" in pset_lower:
        return ["classifications", "material"]

    # ---- Material/constituinte ------------------------------------------
    if facet_type == "material":
        return ["material", "layers", "total_thickness_m"]

    # ---- Quantidades de base --------------------------------------------
    if pset.startswith("Qto_") or facet_type == "quantity":
        return ["width", "height", "length", "volume", "net_side_area", "net_floor_area"]

    # ---- Propriedades térmicas (canônicas + keywords genéricas) ---------
    _thermal_kw = ("thermal", "transmittance", "conductivity", "u_value", "uvalue",
                   "u-value", "shgc", "solar", "absorptance", "heat", "insulation",
                   "conductance", "resistance", "r_value", "rvalue")
    if any(kw in prop_lower for kw in _thermal_kw):
        return ["material", "thickness", "is_external", "layers", "has_insulation"]

    # ---- Propriedades acústicas -----------------------------------------
    _acoustic_kw = ("acoustic", "sound", "noise", "rw", "dntw", "stc", "decibel",
                    "attenuation", "absorption")
    if any(kw in prop_lower for kw in _acoustic_kw):
        return ["material", "thickness", "is_external", "layers"]

    # ---- Propriedades de fogo -------------------------------------------
    _fire_kw = ("fire", "flame", "combusti", "rei", "trrf", "ignition",
                "flammability", "smoke")
    if any(kw in prop_lower for kw in _fire_kw):
        return ["material", "thickness", "is_external"]

    # ---- Propriedades estruturais / carga --------------------------------
    _structural_kw = ("load", "bearing", "structural", "strength", "stress",
                      "stiffness", "modulus", "compressive", "tensile", "yield")
    if any(kw in prop_lower for kw in _structural_kw):
        return ["material", "thickness", "is_external"]

    # ---- Dimensões / geometria ------------------------------------------
    _geo_kw = ("area", "volume", "length", "width", "height", "perimeter",
               "depth", "thickness", "dimension", "size", "span")
    if any(kw in prop_lower for kw in _geo_kw):
        return ["width", "height", "length", "volume", "net_side_area"]

    # ---- Contexto mínimo garantido: sempre entregue material ------------
    return ["material", "total_thickness_m"]


def _infer_unit(req: dict[str, str]) -> str | None:
    """Infere unidade base para o requisito, quando aplicável."""
    prop = req.get("prop", "")
    if prop == "ThermalTransmittance":
        return "W/(m².K)"
    if prop in {"NetFloorArea", "GrossFloorArea", "Area"}:
        return "m²"
    if prop in {"Volume"}:
        return "m³"
    if prop in {"Height", "Width", "Thickness"}:
        return "m"
    return None


def generate_rules(
    specs: list[IDSSpecification],
    profile: ReadinessProfile | None = None,
) -> list[OperationalRule]:
    """Converte IDSSpecifications em OperationalRules verificáveis no IFC.

    Cada requisito de uma spec gera uma OperationalRule independente.
    A entidade é convertida de formato IDS uppercase ("IFCWALL") para
    o formato IfcOpenShell ("IfcWall").

    Se profile for fornecido, cada regra recebe profile_id e tags derivados do perfil.
    suggestion_strategy, write_action e required_context são inferidos automaticamente
    a partir do tipo de check e do contexto do requisito.
    """
    rules: list[OperationalRule] = []

    for spec in specs:
        filter_entity = _to_ifc_class(spec.applicability_entity)
        filter_conditions = _build_filter_conditions(spec.applicability_filters)

        for req in spec.requirements:
            check_type = _infer_check_type(req)
            issue_type = _infer_issue_type(req, filter_entity)
            severity = _infer_severity(req)
            suggestion_strategy = _infer_suggestion_strategy(spec, req)
            write_action = _infer_write_action(spec, req)
            required_context = _infer_required_context(spec, req)

            constraint = req.get("constraint", "")
            expected_value: str | None = None
            if constraint.startswith("equals:"):
                expected_value = constraint[len("equals:"):]

            profile_id: str | None = profile.id if profile else None
            tags: list[str] = [profile.id] if profile else []
            facet_type = req.get("facet_type", "")
            if profile is not None:
                if facet_type:
                    tags.append(f"facet:{facet_type}")
                tags.extend(f"category:{item}" for item in profile.supported_data_categories if item == facet_type)
                if facet_type == "classification":
                    tags.extend(f"classification:{name}" for name in profile.external_classification_systems)

            rule = OperationalRule(
                source_spec=spec.name,
                filter_entity=filter_entity,
                filter_conditions=filter_conditions,
                check_pset=req.get("pset", ""),
                check_property=req.get("prop", ""),
                check_type=check_type,
                expected_value=expected_value,
                issue_type=issue_type,
                severity=severity,
                normative_ref=spec.description,
                suggestion_strategy=suggestion_strategy,  # type: ignore[arg-type]
                write_action=write_action,  # type: ignore[arg-type]
                required_context=required_context,
                profile_id=profile_id,
                evidence_source=_infer_unit(req),
                tags=tags,
            )
            rules.append(rule)
            logger.debug(
                "Regra gerada: {} — {}.{}",
                rule.id,
                rule.check_pset,
                rule.check_property,
            )

    return rules


def generate_rules_for_profiles(
    specs_by_profile: list[tuple[list[IDSSpecification], ReadinessProfile | None]],
) -> list[OperationalRule]:
    """Gera regras a partir de múltiplos conjuntos de IDS/perfis."""
    rules: list[OperationalRule] = []
    for specs, profile in specs_by_profile:
        rules.extend(generate_rules(specs, profile=profile))
    return rules


# ---------------------------------------------------------------------------
# apply_rules helpers
# ---------------------------------------------------------------------------

def _normalize_bool(value: str) -> bool | None:
    """Converte string "TRUE"/"FALSE" para bool Python."""
    upper = value.upper()
    if upper == "TRUE":
        return True
    if upper == "FALSE":
        return False
    return None


_NUMERIC_WITH_UNIT_RE = re.compile(
    r"^\s*([-+]?\d+(?:[.,]\d+)?)\s*([^\d\s].*?)?\s*$"
)


def _normalize_unit(unit: str | None) -> str | None:
    """Normaliza grafias equivalentes de unidades para comparaÃ§Ã£o."""
    if unit is None:
        return None

    normalized = (
        unit.strip()
        .replace(" ", "")
        .replace("·", ".")
        .replace("²", "2")
        .replace("³", "3")
    )
    return normalized.casefold() or None


def normalize_numeric_value(value: str, expected_unit: str | None) -> float | None:
    """Converte uma string numÃ©rica para float normalizado na unidade esperada."""
    match = _NUMERIC_WITH_UNIT_RE.match(str(value))
    if match is None:
        return None

    number_str, source_unit_raw = match.groups()
    try:
        number = float(number_str.replace(",", "."))
    except ValueError:
        return None

    expected = _normalize_unit(expected_unit)
    source = _normalize_unit(source_unit_raw)

    if source is None or expected is None or source == expected:
        return number

    conversions = {
        ("mm", "m"): lambda v: v / 1000.0,
        ("m", "mm"): lambda v: v * 1000.0,
    }
    conversion = conversions.get((source, expected))
    if conversion is not None:
        return conversion(number)

    return None


def _matches_filter(
    element: ifcopenshell.entity_instance,
    conditions: list[dict[str, str]],
    ifc_file: ifcopenshell.file | None = None,
    psets_cache: dict[str, dict[str, dict]] | None = None,
) -> bool:
    """Verifica se um elemento satisfaz TODAS as filter_conditions.

    Delega a avaliação de cada condição para _evaluate_condition.
    Operadores suportados: "EXISTS", "NOT_EXISTS", "==", "!=", "CONTAINS".
    """
    if not conditions:
        return True

    _ifc: ifcopenshell.file = ifc_file or element.wrapped_data.file
    for condition in conditions:
        try:
            if not _evaluate_condition(element, condition, _ifc, psets_cache):
                return False
        except Exception:
            return False

    return True


def _get_pset_value(
    element: ifcopenshell.entity_instance,
    pset_name: str,
    prop_name: str,
    psets_cache: dict[str, dict[str, dict]] | None = None,
) -> Any:
    """Retorna o valor de uma propriedade ou atributo de um elemento IFC.

    Convenções:
        pset_name == ""             → atributo direto via getattr (ex: LongName, Name)
        pset_name == "IFC_RELATION" → não aplicável aqui; retorna None
        outros                      → busca via resolve_property (suporta aliases e Psets alternativos)

    Se ``psets_cache`` for fornecido, evita reconstruir o dicionário de psets para o mesmo
    elemento entre chamadas (cache por GlobalId), eliminando custo O(R) em apply_rules.
    """
    if pset_name == _PSET_ATTRIBUTE:
        return getattr(element, prop_name, None)

    if pset_name == _PSET_RELATION:
        return None

    value, _found_pset, _found_prop, _exact = resolve_property(
        element, pset_name, prop_name, psets_cache
    )
    return value


def _evaluate_condition(
    element: ifcopenshell.entity_instance,
    condition: dict[str, str],
    ifc_file: ifcopenshell.file,
    psets_cache: dict[str, dict[str, dict]] | None = None,
) -> bool:
    """Avalia se um elemento satisfaz uma condition dict.

    Operadores suportados:
        "EXISTS"     → propriedade existe e não é None
        "NOT_EXISTS" → propriedade é None ou ausente
        "=="         → valor == condition["value"] (com normalização booleana)
        "!="         → valor != condition["value"] (com normalização booleana)
        "CONTAINS"   → str(valor) contém condition["value"] (case-insensitive)

    Atributos diretos (pset == "") são lidos via getattr.
    Propriedades de Pset são lidas via get_psets().
    Operador desconhecido → True (comportamento conservador).
    """
    pset = condition.get("pset", "")
    prop = condition.get("prop", "")
    operator = condition.get("operator", "EXISTS")
    expected_raw = condition.get("value", "")

    value = _get_pset_value(element, pset, prop, psets_cache)

    if operator == "EXISTS":
        return value is not None

    if operator == "NOT_EXISTS":
        return value is None

    if operator in ("==", "!="):
        normalized_expected = _normalize_bool(expected_raw)
        if normalized_expected is not None:
            match = (value == normalized_expected)
        else:
            match = (str(value) == expected_raw)
        return match if operator == "==" else not match

    if operator == "CONTAINS":
        if value is None:
            return False
        return expected_raw.lower() in str(value).lower()

    return True


def _passes_check(
    element: ifcopenshell.entity_instance,
    pset_name: str,
    prop_name: str,
    check_type: str,
    expected_value: str | None = None,
    expected_unit: str | None = None,
    psets_cache: dict[str, dict[str, dict]] | None = None,
) -> bool:
    """Verifica se o elemento passa no check definido pela regra.

    Relações IFC (pset_name == "IFC_RELATION") são ignoradas aqui —
    tratadas por relation_diagnostics.
    """
    if pset_name == _PSET_RELATION:
        return True

    value = _get_pset_value(element, pset_name, prop_name, psets_cache)

    if check_type == "exists":
        return value is not None

    if check_type == "is_numeric":
        if isinstance(value, bool) or value is None:
            return False
        normalized_value = normalize_numeric_value(str(value), expected_unit)
        return normalized_value is not None and normalized_value > 0

    if check_type == "is_boolean":
        return isinstance(value, bool)

    if check_type == "not_empty":
        if value is None:
            return False
        return str(value).strip() != ""

    if check_type == "equals":
        if expected_value is None:
            return value is not None
        normalized_actual = None if value is None else normalize_numeric_value(str(value), expected_unit)
        normalized_expected = normalize_numeric_value(expected_value, expected_unit)
        if normalized_actual is not None and normalized_expected is not None:
            return math.isclose(normalized_actual, normalized_expected, rel_tol=1e-9, abs_tol=1e-9)
        normalized = _normalize_bool(expected_value)
        if normalized is not None:
            return value == normalized
        return str(value) == expected_value

    return True


def apply_rules(
    ifc_file: ifcopenshell.file,
    rules: list[OperationalRule],
) -> list[Issue]:
    """Executa as regras sobre o modelo IFC e retorna Issues para falhas.

    Para cada regra:
        1. Busca elementos do tipo filter_entity
        2. Filtra pelos filter_conditions
        3. Verifica o check em cada elemento filtrado
        4. Cria Issue para cada falha (deduplicado por guid + pset + prop)
    """
    issues: list[Issue] = []
    seen: set[tuple[str, str, str]] = set()
    psets_cache: dict[str, dict[str, dict]] = {}
    elements_by_type: dict[str, list] = {}

    for rule in rules:
        elements = elements_by_type.get(rule.filter_entity)
        if elements is None:
            try:
                elements = ifc_file.by_type(rule.filter_entity)
            except Exception as exc:
                logger.warning(
                    "Não foi possível buscar elementos do tipo {}: {}",
                    rule.filter_entity,
                    exc,
                )
                elements_by_type[rule.filter_entity] = []
                continue
            elements_by_type[rule.filter_entity] = elements

        for element in elements:
            if not _matches_filter(element, rule.filter_conditions, ifc_file, psets_cache):
                continue

            if _passes_check(
                element,
                rule.check_pset,
                rule.check_property,
                rule.check_type,
                rule.expected_value,
                rule.evidence_source,
                psets_cache,
            ):
                continue

            dedup_key = (element.GlobalId, rule.check_pset, rule.check_property)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            short_guid = element.GlobalId[:8]
            description = (
                f"{rule.filter_entity} #{short_guid}: "
                f"{rule.check_pset}.{rule.check_property} — regra '{rule.source_spec}'"
            )

            issue = Issue(
                element_guid=element.GlobalId,
                element_class=element.is_a(),
                element_name=getattr(element, "Name", None),
                issue_type=rule.issue_type,  # type: ignore[arg-type]
                severity=rule.severity,
                description=description,
                context={
                    "rule_id": rule.id,
                    "source_spec": rule.source_spec,
                    "check_pset": rule.check_pset,
                    "check_property": rule.check_property,
                    "check_type": rule.check_type,
                    "expected_value": rule.expected_value,
                    "unit": rule.evidence_source,
                    "normative_ref": rule.normative_ref,
                    "ids_context": rule.to_ids_context().model_dump(),
                },
            )
            issues.append(issue)
            logger.debug(
                "Issue criado: {} — {} guid={}",
                issue.id,
                description,
                element.GlobalId[:8],
            )

    return issues
