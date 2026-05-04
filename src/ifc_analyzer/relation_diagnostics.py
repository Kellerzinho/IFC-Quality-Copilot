"""Diagnóstico de relações espaciais quebradas em modelos IFC."""

from typing import Any

import ifcopenshell
from loguru import logger

from src.models import Issue

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# Classes verificadas para ausência de IfcRelFillsElement
_FILLING_CLASSES: tuple[str, ...] = ("IfcDoor", "IfcWindow")

# Classes verificadas para contenção espacial
_ORPHAN_CLASSES: tuple[str, ...] = (
    "IfcDoor",
    "IfcWindow",
    "IfcFurnishingElement",
    "IfcFlowTerminal",
)

# Classes incluídas no cálculo de cobertura de IfcRelSpaceBoundary
_BOUNDARY_COVERAGE_CLASSES: tuple[str, ...] = ("IfcWall", "IfcDoor", "IfcWindow")

# Limiar mínimo de cobertura; abaixo disso emite issue informativo
_BOUNDARY_COVERAGE_THRESHOLD: float = 0.10


# ---------------------------------------------------------------------------
# Funções auxiliares — índices
# ---------------------------------------------------------------------------


def _build_fills_set(ifc_file: ifcopenshell.file) -> set[str]:
    """Retorna conjunto de GUIDs de elementos com IfcRelFillsElement apontando para eles."""
    filled: set[str] = set()
    for rel in ifc_file.by_type("IfcRelFillsElement"):
        element = rel.RelatedBuildingElement
        if element is not None:
            filled.add(element.GlobalId)
    return filled


def _build_contained_set(ifc_file: ifcopenshell.file) -> set[str]:
    """Retorna conjunto de GUIDs de elementos que possuem alguma contenção espacial."""
    contained: set[str] = set()
    for rel in ifc_file.by_type("IfcRelContainedInSpatialStructure"):
        for element in rel.RelatedElements or []:
            contained.add(element.GlobalId)
    return contained


def _build_wall_host_index(ifc_file: ifcopenshell.file) -> dict[str, str]:
    """Retorna mapeamento element_guid → wall_guid via IfcRelFillsElement → IfcRelVoidsElement."""
    # opening_guid → wall_guid
    opening_to_wall: dict[str, str] = {}
    for rel in ifc_file.by_type("IfcRelVoidsElement"):
        wall = rel.RelatingBuildingElement
        opening = rel.RelatedOpeningElement
        if wall is not None and opening is not None:
            opening_to_wall[opening.GlobalId] = wall.GlobalId

    # element_guid → wall_guid
    element_to_wall: dict[str, str] = {}
    for rel in ifc_file.by_type("IfcRelFillsElement"):
        element = rel.RelatedBuildingElement
        opening = rel.RelatingOpeningElement
        if element is not None and opening is not None:
            wall_guid = opening_to_wall.get(opening.GlobalId)
            if wall_guid:
                element_to_wall[element.GlobalId] = wall_guid

    return element_to_wall


def _build_storey_to_spaces(ifc_file: ifcopenshell.file) -> dict[str, list[dict[str, str]]]:
    """Retorna mapeamento storey_guid → lista de {guid, name} dos espaços contidos."""
    storey_spaces: dict[str, list[dict[str, str]]] = {}
    for rel in ifc_file.by_type("IfcRelContainedInSpatialStructure"):
        structure = rel.RelatingStructure
        if structure is None or not structure.is_a("IfcBuildingStorey"):
            continue
        storey_guid = structure.GlobalId
        for element in rel.RelatedElements or []:
            if element.is_a("IfcSpace"):
                storey_spaces.setdefault(storey_guid, []).append(
                    {
                        "guid": element.GlobalId,
                        "name": (
                            getattr(element, "LongName", None)
                            or getattr(element, "Name", None)
                            or ""
                        ),
                    }
                )
    return storey_spaces


def _build_element_to_storey(ifc_file: ifcopenshell.file) -> dict[str, str]:
    """Retorna mapeamento element_guid → storey_guid para todos os elementos contidos."""
    element_storey: dict[str, str] = {}
    for rel in ifc_file.by_type("IfcRelContainedInSpatialStructure"):
        structure = rel.RelatingStructure
        if structure is None:
            continue
        if structure.is_a("IfcBuildingStorey"):
            storey_guid = structure.GlobalId
        else:
            continue
        for element in rel.RelatedElements or []:
            element_storey[element.GlobalId] = storey_guid
    return element_storey


# ---------------------------------------------------------------------------
# Funções auxiliares — contexto
# ---------------------------------------------------------------------------


def _get_nearby_spaces(
    element: ifcopenshell.entity_instance,
    element_to_storey: dict[str, str],
    storey_to_spaces: dict[str, list[dict[str, str]]],
    ifc_file: ifcopenshell.file,
) -> list[dict[str, str]]:
    """Retorna espaços no mesmo storey que o elemento, ou do primeiro storey disponível."""
    storey_guid = element_to_storey.get(element.GlobalId)

    if storey_guid is None:
        # Elemento órfão: usar o primeiro storey disponível
        storeys = ifc_file.by_type("IfcBuildingStorey")
        if storeys:
            storey_guid = storeys[0].GlobalId
        else:
            return []

    return storey_to_spaces.get(storey_guid, [])


def _make_issue(
    element: ifcopenshell.entity_instance,
    severity: str,
    description: str,
    expected_relation: str,
    wall_host_guid: str | None,
    nearby_spaces: list[dict[str, str]],
) -> Issue:
    """Cria um Issue de relação quebrada para um elemento."""
    return Issue(
        element_guid=element.GlobalId,
        element_class=element.is_a(),
        element_name=getattr(element, "Name", None),
        issue_type="relation_broken",
        severity=severity,  # type: ignore[arg-type]
        description=description,
        context={
            "element_guid": element.GlobalId,
            "element_class": element.is_a(),
            "element_name": getattr(element, "Name", None) or "",
            "expected_relation": expected_relation,
            "wall_host_guid": wall_host_guid,
            "nearby_spaces": nearby_spaces,
        },
    )


# ---------------------------------------------------------------------------
# Verificação 1 — IfcRelFillsElement ausente
# ---------------------------------------------------------------------------


def _check_fills_element(
    ifc_file: ifcopenshell.file,
    fills_set: set[str],
    element_to_storey: dict[str, str],
    storey_to_spaces: dict[str, list[dict[str, str]]],
    issues: list[Issue],
) -> None:
    """Cria issues para IfcDoor e IfcWindow sem IfcRelFillsElement."""
    for ifc_class in _FILLING_CLASSES:
        for element in ifc_file.by_type(ifc_class):
            if element.GlobalId in fills_set:
                continue

            nearby = _get_nearby_spaces(element, element_to_storey, storey_to_spaces, ifc_file)
            short_guid = element.GlobalId[:8]
            name = getattr(element, "Name", None) or ""

            issues.append(
                _make_issue(
                    element=element,
                    severity="high",
                    description=(
                        f"{element.is_a()} #{short_guid} '{name}' "
                        f"sem IfcRelFillsElement: não está inserido em nenhuma parede/abertura"
                    ),
                    expected_relation="IfcRelFillsElement",
                    wall_host_guid=None,
                    nearby_spaces=nearby,
                )
            )
            logger.debug(
                f"relation_broken (fills): {element.is_a()} #{short_guid} sem IfcRelFillsElement"
            )


# ---------------------------------------------------------------------------
# Verificação 2 — Elementos órfãos
# ---------------------------------------------------------------------------


def _check_orphan_elements(
    ifc_file: ifcopenshell.file,
    contained_set: set[str],
    element_to_storey: dict[str, str],
    storey_to_spaces: dict[str, list[dict[str, str]]],
    issues: list[Issue],
) -> None:
    """Cria issues para elementos sem nenhuma contenção espacial."""
    for ifc_class in _ORPHAN_CLASSES:
        for element in ifc_file.by_type(ifc_class):
            if element.GlobalId in contained_set:
                continue

            nearby = _get_nearby_spaces(element, element_to_storey, storey_to_spaces, ifc_file)
            short_guid = element.GlobalId[:8]
            name = getattr(element, "Name", None) or ""

            issues.append(
                _make_issue(
                    element=element,
                    severity="medium",
                    description=(
                        f"{element.is_a()} #{short_guid} '{name}' "
                        f"não está contido em nenhuma estrutura espacial (IfcRelContainedInSpatialStructure)"
                    ),
                    expected_relation="IfcRelContainedInSpatialStructure",
                    wall_host_guid=None,
                    nearby_spaces=nearby,
                )
            )
            logger.debug(
                f"relation_broken (orphan): {element.is_a()} #{short_guid} sem contenção espacial"
            )


# ---------------------------------------------------------------------------
# Verificação 3 — Cobertura de IfcRelSpaceBoundary
# ---------------------------------------------------------------------------


def _check_space_boundary_coverage(
    ifc_file: ifcopenshell.file,
) -> Issue | None:
    """Emite 1 issue geral se menos de 10% dos elementos têm IfcRelSpaceBoundary."""
    total = sum(len(ifc_file.by_type(c)) for c in _BOUNDARY_COVERAGE_CLASSES)
    if total == 0:
        return None

    elements_with_boundary: set[str] = set()
    for rel in ifc_file.by_type("IfcRelSpaceBoundary"):
        be = rel.RelatedBuildingElement
        if be is not None:
            elements_with_boundary.add(be.GlobalId)

    count = len(elements_with_boundary)
    coverage = count / total

    if coverage >= _BOUNDARY_COVERAGE_THRESHOLD:
        return None

    projects = ifc_file.by_type("IfcProject")
    if not projects:
        logger.warning("Não foi possível criar issue de cobertura: IfcProject não encontrado")
        return None

    pct = int(coverage * 100)
    logger.warning(
        f"Baixa cobertura de IfcRelSpaceBoundary: {count}/{total} ({pct}%)"
    )

    return Issue(
        element_guid=projects[0].GlobalId,
        element_class="IfcProject",
        element_name=getattr(projects[0], "Name", None),
        issue_type="relation_broken",
        severity="low",
        description=(
            f"Modelo com baixa cobertura de IfcRelSpaceBoundary: "
            f"{count}/{total} elementos ({pct}%)"
        ),
        context={
            "element_guid": projects[0].GlobalId,
            "element_class": "IfcProject",
            "element_name": getattr(projects[0], "Name", None) or "",
            "expected_relation": "IfcRelSpaceBoundary",
            "wall_host_guid": None,
            "nearby_spaces": [],
            "elements_with_boundary": count,
            "total_elements": total,
            "coverage_pct": pct,
        },
    )


# ---------------------------------------------------------------------------
# Diagnóstico principal
# ---------------------------------------------------------------------------


def diagnose_relations(ifc_file: ifcopenshell.file) -> list[Issue]:
    """Diagnostica relações espaciais quebradas: portas/janelas sem vínculo com parede ou espaço."""
    issues: list[Issue] = []

    # Construir índices uma única vez para evitar iterações repetidas
    fills_set = _build_fills_set(ifc_file)
    contained_set = _build_contained_set(ifc_file)
    storey_to_spaces = _build_storey_to_spaces(ifc_file)
    element_to_storey = _build_element_to_storey(ifc_file)

    logger.debug(
        f"Índices de relações: {len(fills_set)} fills, {len(contained_set)} contidos"
    )

    _check_fills_element(ifc_file, fills_set, element_to_storey, storey_to_spaces, issues)
    _check_orphan_elements(ifc_file, contained_set, element_to_storey, storey_to_spaces, issues)

    coverage_issue = _check_space_boundary_coverage(ifc_file)
    if coverage_issue is not None:
        issues.append(coverage_issue)

    return issues
