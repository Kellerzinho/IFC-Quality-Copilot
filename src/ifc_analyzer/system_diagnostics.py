"""Diagnóstico de classificação de sistema construtivo para paredes e lajes IFC."""

from typing import Any

import ifcopenshell
import ifcopenshell.util.element
from loguru import logger

from src.models import Issue

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# Classes de elemento verificadas
_TARGET_CLASSES: tuple[str, ...] = ("IfcWall", "IfcSlab")

# Psets padrão IFC que identificam o sistema de material
_STANDARD_MATERIAL_PSETS: frozenset[str] = frozenset(
    {
        "Pset_MaterialConcrete",
        "Pset_MaterialMetal",
        "Pset_MaterialSteel",
        "Pset_MaterialWood",
        "Pset_MaterialTimber",
        "Pset_MaterialGlass",
        "Pset_MaterialMasonry",
    }
)

# Palavras-chave para detectar Psets customizados com dados de material
_CUSTOM_MATERIAL_KEYWORDS: tuple[str, ...] = (
    "material",
    "finish",
    "construction",
    "revit_mat",
    "akitabox",
    "assembly",
)


# ---------------------------------------------------------------------------
# Extração de material e camadas
# ---------------------------------------------------------------------------


def _extract_material_layers(
    element: ifcopenshell.entity_instance,
) -> list[dict[str, Any]]:
    """Retorna lista de {name, thickness_m} para as camadas de material do elemento."""
    try:
        material = ifcopenshell.util.element.get_material(element)
        if material is None:
            return []

        if material.is_a("IfcMaterialLayerSetUsage"):
            return _layers_from_set(material.ForLayerSet)
        if material.is_a("IfcMaterialLayerSet"):
            return _layers_from_set(material)
        if material.is_a("IfcMaterial"):
            return [{"name": material.Name, "thickness_m": None}]

    except Exception as exc:
        logger.warning(f"Erro ao extrair camadas de material de {element.GlobalId}: {exc}")
    return []


def _layers_from_set(
    layer_set: ifcopenshell.entity_instance,
) -> list[dict[str, Any]]:
    """Converte um IfcMaterialLayerSet em lista de dicts {name, thickness_m}."""
    layers = []
    for layer in layer_set.MaterialLayers or []:
        layers.append(
            {
                "name": layer.Material.Name if layer.Material else None,
                "thickness_m": float(layer.LayerThickness or 0.0),
            }
        )
    return layers


def _total_thickness(layers: list[dict[str, Any]]) -> float | None:
    """Retorna espessura total somando as camadas; None se lista vazia."""
    if not layers:
        return None
    total = sum(
        (lay["thickness_m"] or 0.0) for lay in layers if lay["thickness_m"] is not None
    )
    return total if total > 0.0 else None


# ---------------------------------------------------------------------------
# Verificações de classificação
# ---------------------------------------------------------------------------


def _get_classification(
    element: ifcopenshell.entity_instance,
    ifc_file: ifcopenshell.file,
) -> tuple[bool, str | None]:
    """Retorna (has_classification, nome_da_classificação) via IfcRelAssociatesClassification."""
    try:
        for rel in ifc_file.by_type("IfcRelAssociatesClassification"):
            if element not in (rel.RelatedObjects or []):
                continue
            cls_ref = rel.RelatingClassification
            if cls_ref is None:
                continue
            # IFC2X3: ItemReference / IFC4: Identification
            name = (
                getattr(cls_ref, "Name", None)
                or getattr(cls_ref, "Identification", None)
                or getattr(cls_ref, "ItemReference", None)
            )
            return True, str(name) if name else None
    except Exception as exc:
        logger.warning(f"Erro ao ler classificação de {element.GlobalId}: {exc}")
    return False, None


def _has_standard_material_pset(
    element: ifcopenshell.entity_instance,
) -> bool:
    """Retorna True se algum Pset padrão de material existe no elemento OU nos seus materiais."""
    try:
        # Verificar Psets do próprio elemento
        element_psets = ifcopenshell.util.element.get_psets(element)
        if any(name in _STANDARD_MATERIAL_PSETS for name in element_psets):
            return True

        # Verificar Psets das camadas de material
        material = ifcopenshell.util.element.get_material(element)
        if material is None:
            return False

        if material.is_a("IfcMaterialLayerSetUsage"):
            layer_set = material.ForLayerSet
        elif material.is_a("IfcMaterialLayerSet"):
            layer_set = material
        else:
            layer_set = None

        if layer_set is not None:
            for layer in layer_set.MaterialLayers or []:
                if layer.Material is None:
                    continue
                mat_psets = ifcopenshell.util.element.get_psets(layer.Material)
                if any(name in _STANDARD_MATERIAL_PSETS for name in mat_psets):
                    return True

        if material.is_a("IfcMaterial"):
            mat_psets = ifcopenshell.util.element.get_psets(material)
            if any(name in _STANDARD_MATERIAL_PSETS for name in mat_psets):
                return True

    except Exception as exc:
        logger.warning(f"Erro ao verificar Psets de material de {element.GlobalId}: {exc}")
    return False


def _detect_custom_material_pset(
    psets: dict[str, dict[str, Any]],
) -> bool:
    """Retorna True se há Pset não-padrão com indícios de dados de material."""
    for pset_name, props in psets.items():
        if pset_name.startswith(("Pset_", "Qto_")):
            continue
        name_lower = pset_name.lower()
        if any(kw in name_lower for kw in _CUSTOM_MATERIAL_KEYWORDS):
            return True
        for prop_name in props:
            if isinstance(prop_name, str) and any(
                kw in prop_name.lower() for kw in _CUSTOM_MATERIAL_KEYWORDS
            ):
                return True
    return False


# ---------------------------------------------------------------------------
# Construção de contexto e criação de issue
# ---------------------------------------------------------------------------


def _build_context(
    element: ifcopenshell.entity_instance,
    layers: list[dict[str, Any]],
    has_classification: bool,
    classification_current: str | None,
    has_standard_material_pset: bool,
    has_custom_pset_material: bool,
) -> dict[str, Any]:
    """Monta o dicionário de contexto para o issue."""
    ctx: dict[str, Any] = {
        "materials": layers,
        "total_thickness": _total_thickness(layers),
        "has_classification": has_classification,
        "classification_current": classification_current,
        "has_standard_material_pset": has_standard_material_pset,
        "has_custom_pset_material": has_custom_pset_material,
    }

    # Para IfcSlab: enriquecer com PredefinedType e ObjectType
    if element.is_a("IfcSlab") or element.is_a("IfcSlabStandardCase"):
        predefined_type = getattr(element, "PredefinedType", None)
        object_type = getattr(element, "ObjectType", None)
        ctx["predefined_type"] = str(predefined_type) if predefined_type else "NOTDEFINED"
        ctx["object_type"] = str(object_type) if object_type else None

    return ctx


def _make_system_issue(
    element: ifcopenshell.entity_instance,
    context: dict[str, Any],
) -> Issue:
    """Cria um Issue de sistema construtivo não classificado."""
    short_guid = element.GlobalId[:8]
    element_class = element.is_a()
    element_name = getattr(element, "Name", None)

    hint = ""
    if context["has_custom_pset_material"]:
        hint = " (dados de material encontrados em Pset customizado — considere migrar para Pset padrão)"

    return Issue(
        element_guid=element.GlobalId,
        element_class=element_class,
        element_name=element_name,
        issue_type="system_unclassified",
        severity="medium",
        description=(
            f"{element_class} #{short_guid} sem classificação de sistema construtivo{hint}"
        ),
        context=context,
    )


# ---------------------------------------------------------------------------
# Diagnóstico principal
# ---------------------------------------------------------------------------


def diagnose_systems(ifc_file: ifcopenshell.file) -> list[Issue]:
    """Diagnostica paredes e lajes sem classificação de sistema construtivo."""
    issues: list[Issue] = []

    for ifc_class in _TARGET_CLASSES:
        elements = ifc_file.by_type(ifc_class)
        logger.debug(f"Verificando {len(elements)} {ifc_class}(s) para classificação de sistema")

        for element in elements:
            try:
                _check_element_system(element, ifc_file, issues)
            except Exception as exc:
                logger.warning(
                    f"Erro inesperado ao verificar sistema de {element.GlobalId}: {exc}"
                )

    return issues


def _check_element_system(
    element: ifcopenshell.entity_instance,
    ifc_file: ifcopenshell.file,
    issues: list[Issue],
) -> None:
    """Verifica um elemento e adiciona issue se não possuir classificação de sistema."""
    has_classification, classification_current = _get_classification(element, ifc_file)
    has_std_pset = _has_standard_material_pset(element)

    # Elemento classificado — sem issue
    if has_classification or has_std_pset:
        logger.debug(
            f"{element.is_a()} #{element.GlobalId[:8]}: classificação OK "
            f"(cls={has_classification}, std_pset={has_std_pset})"
        )
        return

    element_psets = ifcopenshell.util.element.get_psets(element)
    has_custom = _detect_custom_material_pset(element_psets)
    layers = _extract_material_layers(element)

    context = _build_context(
        element=element,
        layers=layers,
        has_classification=has_classification,
        classification_current=classification_current,
        has_standard_material_pset=has_std_pset,
        has_custom_pset_material=has_custom,
    )

    issues.append(_make_system_issue(element, context))
    logger.debug(
        f"system_unclassified: {element.is_a()} #{element.GlobalId[:8]} "
        f"(custom_pset={has_custom}, layers={len(layers)})"
    )
