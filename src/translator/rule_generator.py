"""Gerador de OperationalRules a partir de IDSSpecifications."""

from typing import Any, Literal

import ifcopenshell
import ifcopenshell.util.element
from loguru import logger

from src.models import IDSSpecification, Issue, OperationalRule

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


def _to_ifc_class(entity: str) -> str:
    """Converte nome de entidade IDS uppercase para nome de classe IfcOpenShell.

    Exemplos:
        "IFCWALL" → "IfcWall"
        "IFCSPACE" → "IfcSpace"
        "IFCSLAB" → "IfcSlab"
    """
    if not entity.upper().startswith("IFC"):
        return entity
    suffix = entity[3:].capitalize()
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
    pset = req.get("pset", "")

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


def generate_rules(specs: list[IDSSpecification]) -> list[OperationalRule]:
    """Converte IDSSpecifications em OperationalRules verificáveis no IFC.

    Cada requisito de uma spec gera uma OperationalRule independente.
    A entidade é convertida de formato IDS uppercase ("IFCWALL") para
    o formato IfcOpenShell ("IfcWall").
    """
    rules: list[OperationalRule] = []

    for spec in specs:
        filter_entity = _to_ifc_class(spec.applicability_entity)
        filter_conditions = _build_filter_conditions(spec.applicability_filters)

        for req in spec.requirements:
            check_type = _infer_check_type(req)
            issue_type = _infer_issue_type(req, filter_entity)
            severity = _infer_severity(req)

            rule = OperationalRule(
                source_spec=spec.name,
                filter_entity=filter_entity,
                filter_conditions=filter_conditions,
                check_pset=req.get("pset", ""),
                check_property=req.get("prop", ""),
                check_type=check_type,
                issue_type=issue_type,
                severity=severity,
                normative_ref=spec.description,
            )
            rules.append(rule)
            logger.debug(
                "Regra gerada: {} — {}.{}",
                rule.id,
                rule.check_pset,
                rule.check_property,
            )

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


def _matches_filter(
    element: ifcopenshell.entity_instance,
    conditions: list[dict[str, str]],
    ifc_file: ifcopenshell.file | None = None,
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
            if not _evaluate_condition(element, condition, _ifc):
                return False
        except Exception:
            return False

    return True


def _get_pset_value(
    element: ifcopenshell.entity_instance,
    pset_name: str,
    prop_name: str,
) -> Any:
    """Retorna o valor de uma propriedade ou atributo de um elemento IFC.

    Convenções:
        pset_name == ""             → atributo direto via getattr (ex: LongName, Name)
        pset_name == "IFC_RELATION" → não aplicável aqui; retorna None
        outros                      → lê via ifcopenshell.util.element.get_psets()
    """
    if pset_name == _PSET_ATTRIBUTE:
        return getattr(element, prop_name, None)

    if pset_name == _PSET_RELATION:
        return None

    try:
        psets = ifcopenshell.util.element.get_psets(element)
    except Exception:
        return None

    pset_data = psets.get(pset_name)
    if pset_data is None:
        return None
    return pset_data.get(prop_name)


def _evaluate_condition(
    element: ifcopenshell.entity_instance,
    condition: dict[str, str],
    ifc_file: ifcopenshell.file,
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

    value = _get_pset_value(element, pset, prop)

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
) -> bool:
    """Verifica se o elemento passa no check definido pela regra.

    Relações IFC (pset_name == "IFC_RELATION") são ignoradas aqui —
    tratadas por relation_diagnostics.
    """
    if pset_name == _PSET_RELATION:
        return True

    value = _get_pset_value(element, pset_name, prop_name)

    if check_type == "exists":
        return value is not None

    if check_type == "is_numeric":
        return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0

    if check_type == "is_boolean":
        return isinstance(value, bool)

    if check_type == "not_empty":
        if value is None:
            return False
        return str(value).strip() != ""

    if check_type == "equals":
        return value is not None

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

    for rule in rules:
        try:
            elements = ifc_file.by_type(rule.filter_entity)
        except Exception as exc:
            logger.warning(
                "Não foi possível buscar elementos do tipo {}: {}",
                rule.filter_entity,
                exc,
            )
            continue

        for element in elements:
            if not _matches_filter(element, rule.filter_conditions, ifc_file):
                continue

            if _passes_check(element, rule.check_pset, rule.check_property, rule.check_type):
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
                    "check_pset": rule.check_pset,
                    "check_property": rule.check_property,
                    "check_type": rule.check_type,
                    "normative_ref": rule.normative_ref,
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
