"""Diagnóstico de qualidade para IfcSpace no modelo IFC."""

import re
from typing import Any

import ifcopenshell
import ifcopenshell.util.element
from loguru import logger

from src.models import Issue

# Importação opcional de ifcopenshell.geom (pode não estar disponível)
try:
    import ifcopenshell.geom as _ifc_geom
    import ifcopenshell.util.shape as _shape_util

    _HAS_GEOM = True
except Exception:
    _HAS_GEOM = False

# ---------------------------------------------------------------------------
# Padrões de nomes genéricos
# ---------------------------------------------------------------------------

_GENERIC_PATTERNS: list[re.Pattern] = [
    re.compile(r"^Room\s*\d*$", re.IGNORECASE),
    re.compile(r"^Space\s*\d*$", re.IGNORECASE),
    re.compile(r"^Sala\s*\d*$", re.IGNORECASE),
    re.compile(r"^\d+$"),
]

_GENERIC_NAMES_EXACT: frozenset[str] = frozenset({"default", "unnamed"})

# ---------------------------------------------------------------------------
# Mapeamentos de classificação sanitária
# ---------------------------------------------------------------------------

_SANITARY_WC: frozenset[str] = frozenset({"TOILETPAN", "WCSEAT"})
_SANITARY_BASIN: frozenset[str] = frozenset({"WASHHANDBASIN", "WASHBASIN", "SINK"})
_SANITARY_SHOWER: frozenset[str] = frozenset({"SHOWER"})
_SANITARY_BATH: frozenset[str] = frozenset({"BATH", "BATHSIT"})

_WC_KEYWORDS: tuple[str, ...] = ("wc", "toilet", "vaso sanitário", "vaso", "sanitário")
_BASIN_KEYWORDS: tuple[str, ...] = ("lavatório", "lavatorio", "pia", "basin", "lavabo")
_SHOWER_KEYWORDS: tuple[str, ...] = ("chuveiro", "shower", "ducha")
_BATH_KEYWORDS: tuple[str, ...] = ("banheira", "bath", "tina")


# ---------------------------------------------------------------------------
# Funções auxiliares — nomes genéricos
# ---------------------------------------------------------------------------


def _is_generic_name(name: str | None) -> bool:
    """Retorna True se o nome for genérico, vazio, None ou muito curto."""
    if name is None:
        return True
    stripped = name.strip()
    if len(stripped) < 2:
        return True
    if stripped.lower() in _GENERIC_NAMES_EXACT:
        return True
    return any(p.match(stripped) for p in _GENERIC_PATTERNS)


# ---------------------------------------------------------------------------
# Mapeamentos funcionais de mobiliário e equipamentos
# ---------------------------------------------------------------------------

# Cada entrada: (label_funcional, [keywords_no_nome])
_FURNISHING_FUNCTIONAL: list[tuple[str, tuple[str, ...]]] = [
    # Sanitários / banheiro
    ("chuveiro/box",       ("chuveiro", "shower", "box", "ducha", "showerbase", "cabine de banho")),
    ("banheira",           ("banheira", "bath", "bathtub", "tina")),
    ("cuba/lavatório",     ("cuba", "lavatório", "lavatorio", "lavabo", "pia de banheiro",
                            "washbasin", "washhandbasin", "basin")),
    ("armário de banheiro", ("armário de banheiro", "gabinete de banheiro", "espelheira",
                             "bathroom cabinet", "vanity")),
    # Cozinha / área de serviço
    ("fogão/cooktop",      ("fogão", "fogao", "cooktop", "cooker", "stove", "forno",
                            "oven", "fogão embutido", "cooktop embutido")),
    ("pia de cozinha",     ("pia de cozinha", "pia cozinha", "kitchen sink", "kitchensink")),
    ("bancada de cozinha", ("bancada", "balcão de cozinha", "counter", "countertop")),
    ("armário de cozinha", ("armário de cozinha", "gabinete de cozinha", "kitchen cabinet",
                            "armário alto", "armário baixo")),
    ("geladeira",          ("geladeira", "refrigerador", "fridge", "refrigerator")),
    ("micro-ondas",        ("micro-ondas", "microondas", "microwave")),
    # Lavanderia / área de serviço
    ("tanque",             ("tanque", "utility sink", "laundry sink")),
    ("máquina de lavar",   ("máquina de lavar", "maquina de lavar", "washing machine",
                            "washingmachine", "washer", "lavadora")),
    ("secadora",           ("secadora", "dryer", "secador de roupas")),
    # Sala de estar / jantar
    ("sofá/poltrona",      ("sofá", "sofa", "poltrona", "armchair", "loveseat",
                            "sectional", "couch", "divã", "diva")),
    ("televisão",          ("televisão", "televisao", "tv", "television", "monitor",
                            "home theater", "rack de tv", "painel de tv")),
    ("mesa de jantar",     ("mesa de jantar", "dining table", "mesa jantar")),
    ("cadeira de jantar",  ("cadeira de jantar", "dining chair")),
    ("mesa de centro",     ("mesa de centro", "coffee table", "mesa lateral")),
    ("aparador",           ("aparador", "buffet", "sideboard", "credenza")),
    # Dormitório
    ("cama",               ("cama", "bed", "colchão", "colchao", "mattress", "berço",
                            "bercinho", "crib", "solteiro", "casal", "king", "queen")),
    ("guarda-roupa",       ("guarda-roupa", "guarda roupa", "wardrobe", "closet",
                            "roupeiro", "armário de quarto")),
    ("criado-mudo",        ("criado-mudo", "criado mudo", "nightstand", "bedside table")),
    # Escritório / laboratório
    ("mesa de escritório", ("mesa de escritório", "escrivaninha", "desk", "writing desk",
                            "workstation", "mesa de trabalho")),
    ("cadeira de escritório", ("cadeira de escritório", "office chair", "cadeira ergonomica")),
    ("bancada de laboratório", ("bancada de laboratório", "bancada lab", "lab bench",
                                "laboratory bench", "bancada científica")),
    ("equipamento de laboratório", ("equipamento de laboratório", "lab equipment",
                                    "microscópio", "microscope", "centrifuga", "centrifuge",
                                    "autoclave", "estufa de laboratório")),
    # Geral
    ("estante",            ("estante", "bookshelf", "bookcase", "prateleira", "shelf")),
    ("mesa",               ("mesa", "table")),
    ("cadeira",            ("cadeira", "chair", "banco", "stool")),
]


def _classify_furnishing(name: str) -> str:
    """Retorna label funcional para IfcFurnishingElement com base no nome."""
    name_lower = name.lower()
    for label, keywords in _FURNISHING_FUNCTIONAL:
        if any(kw in name_lower for kw in keywords):
            return label
    return f"mobiliário: {name}" if name else "mobiliário"


def _classify_flow_terminal(name: str) -> str:
    """Retorna label funcional para IfcFlowTerminal com base no nome."""
    name_lower = name.lower()
    for label, keywords in _FURNISHING_FUNCTIONAL:
        if any(kw in name_lower for kw in keywords):
            return label
    return f"equipamento: {name}" if name else "equipamento"


# ---------------------------------------------------------------------------
# Funções auxiliares — classificação funcional de elementos
# ---------------------------------------------------------------------------


def _classify_sanitary_terminal(element: ifcopenshell.entity_instance) -> str:
    """Retorna label funcional para IfcSanitaryTerminal com base no tipo ou nome."""
    # IFC4 usa PredefinedType; IFC2X3 usa SanitaryTerminalType
    raw_type = getattr(element, "PredefinedType", None) or getattr(element, "SanitaryTerminalType", None)
    ptype: str = str(raw_type).upper() if raw_type else ""

    if ptype in _SANITARY_WC:
        return "WC"
    if ptype in _SANITARY_BASIN:
        return "lavatório"
    if ptype in _SANITARY_SHOWER:
        return "chuveiro"
    if ptype in _SANITARY_BATH:
        return "banheira"

    # Fallback por nome
    name_lower = (getattr(element, "Name", None) or "").lower()
    if any(kw in name_lower for kw in _WC_KEYWORDS):
        return "WC"
    if any(kw in name_lower for kw in _BASIN_KEYWORDS):
        return "lavatório"
    if any(kw in name_lower for kw in _SHOWER_KEYWORDS):
        return "chuveiro"
    if any(kw in name_lower for kw in _BATH_KEYWORDS):
        return "banheira"

    name = getattr(element, "Name", None) or ""
    return f"IfcSanitaryTerminal: {name}"


def _get_functional_label(element: ifcopenshell.entity_instance) -> str:
    """Retorna label funcional para um elemento IFC contido em um espaço."""
    name = getattr(element, "Name", None) or ""

    if element.is_a("IfcSanitaryTerminal"):
        return _classify_sanitary_terminal(element)
    if element.is_a("IfcFurnishingElement"):
        return _classify_furnishing(name)
    if element.is_a("IfcFlowTerminal"):
        # Tenta classificar por nome antes de usar label genérico
        classified = _classify_flow_terminal(name)
        if not classified.startswith("equipamento:"):
            return classified
        return classified
    return f"{element.is_a()}: {name}" if name else element.is_a()


# ---------------------------------------------------------------------------
# Funções auxiliares — elementos contidos
# ---------------------------------------------------------------------------


def _extract_contained_elements(
    space: ifcopenshell.entity_instance,
    ifc_file: ifcopenshell.file,
) -> list[dict[str, Any]]:
    """Extrai e classifica elementos diretamente contidos no espaço."""
    contained: list[dict[str, Any]] = []
    try:
        for rel in ifc_file.by_type("IfcRelContainedInSpatialStructure"):
            if rel.RelatingStructure != space:
                continue
            for element in rel.RelatedElements or []:
                contained.append(
                    {
                        "guid": element.GlobalId,
                        "ifc_class": element.is_a(),
                        "functional_label": _get_functional_label(element),
                        "name": getattr(element, "Name", None) or "",
                    }
                )
    except Exception as exc:
        logger.warning(
            f"Erro ao extrair elementos contidos do espaço {space.GlobalId}: {exc}"
        )
    return contained


# ---------------------------------------------------------------------------
# Funções auxiliares — adjacências
# ---------------------------------------------------------------------------


def _get_adjacent_via_doors(
    space: ifcopenshell.entity_instance,
    ifc_file: ifcopenshell.file,
    already_seen: set[str],
) -> list[dict[str, Any]]:
    """Retorna espaços adjacentes via portas compartilhadas (fallback sem IfcRelSpaceBoundary).

    Busca portas diretamente contidas neste espaço e verifica se as mesmas
    portas estão contidas em outro IfcSpace, indicando adjacência.
    """
    adjacent: list[dict[str, Any]] = []

    containment_rels = ifc_file.by_type("IfcRelContainedInSpatialStructure")
    space_door_guids: set[str] = set()
    for rel in containment_rels:
        if rel.RelatingStructure == space:
            for element in rel.RelatedElements or []:
                if element.is_a("IfcDoor"):
                    space_door_guids.add(element.GlobalId)

    if not space_door_guids:
        return adjacent

    for rel in containment_rels:
        other_structure = rel.RelatingStructure
        if not other_structure.is_a("IfcSpace") or other_structure == space:
            continue
        for element in rel.RelatedElements or []:
            if element.GlobalId not in space_door_guids:
                continue
            guid = other_structure.GlobalId
            if guid not in already_seen:
                already_seen.add(guid)
                adjacent.append(
                    {
                        "guid": guid,
                        "name": (
                            getattr(other_structure, "LongName", None)
                            or getattr(other_structure, "Name", None)
                            or ""
                        ),
                        "connection_type": "door",
                    }
                )
            break  # evita duplicatas da mesma relação

    return adjacent


def _extract_adjacent_spaces(
    space: ifcopenshell.entity_instance,
    ifc_file: ifcopenshell.file,
) -> tuple[list[dict[str, Any]], bool]:
    """Extrai espaços adjacentes e se o espaço tem fronteira com exterior.

    Tenta via IfcRelSpaceBoundary primeiro; usa portas como fallback.
    Retorna (adjacent_spaces, is_on_exterior).
    """
    adjacent: list[dict[str, Any]] = []
    seen: set[str] = set()
    is_exterior = False
    has_boundaries = False

    try:
        boundary_rels = ifc_file.by_type("IfcRelSpaceBoundary")
        spaces_by_boundary_element: dict[str, list[Any]] = {}
        for rel in boundary_rels:
            boundary_element = rel.RelatedBuildingElement
            rel_space = rel.RelatingSpace
            if boundary_element is None or rel_space is None:
                continue
            spaces_by_boundary_element.setdefault(boundary_element.GlobalId, []).append(rel_space)

        for rel in boundary_rels:
            if rel.RelatingSpace != space:
                continue
            has_boundaries = True

            # Verificar exterioridade
            internal_ext = getattr(rel, "InternalOrExternalBoundary", None)
            if internal_ext is not None and str(internal_ext).upper() == "EXTERNAL":
                is_exterior = True

            boundary_element = rel.RelatedBuildingElement
            if boundary_element is None:
                continue

            for other_space in spaces_by_boundary_element.get(boundary_element.GlobalId, []):
                if other_space == space:
                    continue
                guid = other_space.GlobalId
                if guid not in seen:
                    seen.add(guid)
                    adjacent.append(
                        {
                            "guid": guid,
                            "name": (
                                getattr(other_space, "LongName", None)
                                or getattr(other_space, "Name", None)
                                or ""
                            ),
                            "connection_type": "boundary",
                        }
                    )
    except Exception as exc:
        logger.warning(
            f"Erro ao extrair adjacências via boundary do espaço {space.GlobalId}: {exc}"
        )

    if not has_boundaries:
        logger.debug(
            f"Espaço {space.GlobalId} sem IfcRelSpaceBoundary; tentando fallback via portas"
        )
        try:
            door_adjacent = _get_adjacent_via_doors(space, ifc_file, seen)
            adjacent.extend(door_adjacent)
        except Exception as exc:
            logger.warning(
                f"Erro no fallback de portas para espaço {space.GlobalId}: {exc}"
            )

    return adjacent, is_exterior


# ---------------------------------------------------------------------------
# Extração de contexto completo
# ---------------------------------------------------------------------------


def _extract_space_context(
    space: ifcopenshell.entity_instance, ifc_file: ifcopenshell.file
) -> dict[str, Any]:
    """Extrai dados contextuais de um IfcSpace para uso no LLM."""
    context: dict[str, Any] = {}

    # --- Quantidades via Qto_SpaceBaseQuantities ---
    try:
        psets = ifcopenshell.util.element.get_psets(space, qtos_only=True)
        qto = psets.get("Qto_SpaceBaseQuantities", {})
    except Exception as exc:
        logger.warning(f"Erro ao ler Qto_SpaceBaseQuantities do espaço {space.GlobalId}: {exc}")
        qto = {}

    area: float | None = qto.get("NetFloorArea") or qto.get("GrossFloorArea") or None
    context["area_m2"] = area
    context["height_m"] = qto.get("Height") or None
    context["perimeter_m"] = qto.get("Perimeter") or None

    # --- Fallback de área e bounding_box via geometria ---
    bounding_box: dict[str, float] | None = None
    if _HAS_GEOM:
        try:
            settings = _ifc_geom.settings()
            shape = _ifc_geom.create_shape(settings, space)
            if area is None:
                area = _shape_util.get_footprint_area(shape.geometry)
                context["area_m2"] = area
            verts = shape.geometry.verts
            if verts:
                xs = verts[0::3]
                ys = verts[1::3]
                zs = verts[2::3]
                bounding_box = {
                    "min_x": min(xs), "max_x": max(xs),
                    "min_y": min(ys), "max_y": max(ys),
                    "min_z": min(zs), "max_z": max(zs),
                }
        except Exception:
            pass  # geometria indisponível em modelos sem representação
    context["bounding_box"] = bounding_box

    # --- Elementos contidos ---
    context["contained_elements"] = _extract_contained_elements(space, ifc_file)

    # --- Adjacências e exterioridade ---
    adjacent, is_exterior = _extract_adjacent_spaces(space, ifc_file)
    context["adjacent_spaces"] = adjacent
    context["is_on_exterior"] = is_exterior

    # --- Pavimento pai ---
    floor_name: str | None = None
    try:
        for rel in ifc_file.by_type("IfcRelContainedInSpatialStructure"):
            if space in (rel.RelatedElements or []):
                structure = rel.RelatingStructure
                if structure is not None and structure.is_a("IfcBuildingStorey"):
                    floor_name = getattr(structure, "Name", None)
                    break
    except Exception as exc:
        logger.warning(f"Erro ao determinar pavimento do espaço {space.GlobalId}: {exc}")
    context["floor"] = floor_name

    return context


# ---------------------------------------------------------------------------
# Diagnóstico principal
# ---------------------------------------------------------------------------


def diagnose_spaces(ifc_file: ifcopenshell.file) -> list[Issue]:
    """Diagnostica IfcSpaces com nomes genéricos ou vazios."""
    issues: list[Issue] = []

    spaces = ifc_file.by_type("IfcSpace")
    logger.debug(f"Analisando {len(spaces)} IfcSpace(s)")

    for space in spaces:
        long_name: str | None = getattr(space, "LongName", None)
        name: str | None = getattr(space, "Name", None)

        # LongName preferencial; fallback para Name
        display_name: str | None = long_name if long_name else name
        label = display_name if display_name and display_name.strip() else "(sem nome)"

        if not _is_generic_name(display_name):
            continue

        logger.debug(f"Espaço genérico detectado: guid={space.GlobalId!r}, nome={label!r}")

        context = _extract_space_context(space, ifc_file)

        issues.append(
            Issue(
                element_guid=space.GlobalId,
                element_class="IfcSpace",
                element_name=label,
                issue_type="space_unnamed",
                severity="low",
                description=f"Espaço '{label}' não possui nome funcional",
                context=context,
            )
        )

    return issues
