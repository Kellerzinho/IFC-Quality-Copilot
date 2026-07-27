"""Diagnóstico de qualidade para Psets obrigatórios em elementos IFC."""

from typing import Any

import ifcopenshell
import ifcopenshell.util.element
from loguru import logger

from src.ifc_analyzer.material_reader import read_material_layers
from src.models import Issue
from src.ifc_analyzer.space_diagnostics import (
    _extract_contained_elements,
    _extract_adjacent_spaces,
)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

DEFAULT_REQUIRED_PSETS: dict[str, dict[str, list[str]]] = {
    "IfcWall": {
        "Pset_WallCommon": [
            "ThermalTransmittance",
            "IsExternal",
            "FireRating",
            "IsLoadBearing",
            "AcousticRating",
        ],
    },
    "IfcSlab": {
        "Pset_SlabCommon": [
            "IsExternal",
            "LoadBearing",
            "ThermalTransmittance",
            "FireRating",
        ],
    },
    "IfcDoor": {
        "Pset_DoorCommon": [
            "FireRating",
            "IsExternal",
            "AcousticRating",
        ],
    },
    "IfcWindow": {
        "Pset_WindowCommon": [
            "ThermalTransmittance",
            "IsExternal",
            "SolarHeatGainCoefficient",
        ],
    },
    "IfcSpace": {
        "Pset_SpaceCommon": ["Category"],
    },
    "IfcBeam": {
        "Pset_BeamCommon": [
            "FireRating",
            "LoadBearing",
            "IsExternal",
        ],
    },
    "IfcColumn": {
        "Pset_ColumnCommon": [
            "FireRating",
            "LoadBearing",
            "IsExternal",
        ],
    },
    "IfcRoof": {
        "Pset_RoofCommon": [
            "ThermalTransmittance",
            "FireRating",
            "IsExternal",
        ],
    },
    "IfcStair": {
        "Pset_StairCommon": [
            "FireRating",
            "HasNonSkidSurface",
        ],
    },
    "IfcCurtainWall": {
        "Pset_CurtainWallCommon": [
            "ThermalTransmittance",
            "IsExternal",
            "FireRating",
        ],
    },
}

# Propriedades cuja ausência é severidade alta (impede simulação ou verificação normativa)
_HIGH_SEVERITY_PROPERTIES: frozenset[str] = frozenset({
    "ThermalTransmittance",
    "FireRating",
    "SolarHeatGainCoefficient",
    "LoadBearing",
})

# Propriedades numéricas onde 0.0 é fisicamente impossível ou sem sentido
_ZERO_IS_INVALID: frozenset[str] = frozenset({
    "ThermalTransmittance",
    "SolarHeatGainCoefficient",
})


# ---------------------------------------------------------------------------
# Funções auxiliares — validação de valor
# ---------------------------------------------------------------------------


def _is_empty_value(value: Any, prop_name: str) -> bool:
    """Retorna True se o valor é considerado ausente ou inválido para a propriedade.

    Trata None, string vazia e 0.0 em propriedades onde zero não faz sentido.
    Booleans False são considerados válidos (IsExternal=False é informação útil).
    """
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    if isinstance(value, float) and value == 0.0 and prop_name in _ZERO_IS_INVALID:
        return True
    return False


# ---------------------------------------------------------------------------
# Funções auxiliares — extração de material
# ---------------------------------------------------------------------------


def _extract_element_material_context(
    element: ifcopenshell.entity_instance,
    ifc_file: ifcopenshell.file,
) -> dict[str, Any]:
    """Extrai material, espessura total e camadas de um elemento IFC.

    Delega ao leitor unificado, que entende também ``IfcMaterialConstituentSet``
    (formato do Revit) e busca a espessura no conjunto de quantidades. Sem isso,
    as 606 issues de ``ThermalTransmittance`` do prédio chegavam ao LLM com
    ``thickness_m=None`` — e não há como estimar U sem espessura.
    """
    leitura = read_material_layers(element)
    return {
        "material_name": leitura.material_name,
        "thickness_m": leitura.total_thickness_m,
        # A chave da camada aqui é "material" (não "name"): é o que os templates
        # de prompt e a assinatura de cache já consomem.
        "layers": [
            {"material": camada["name"], "thickness_m": camada["thickness_m"]}
            for camada in leitura.layers
        ],
    }


def _fill_from_layer_set(
    layer_set: ifcopenshell.entity_instance,
    context: dict[str, Any],
) -> None:
    """Preenche context com dados extraídos de um IfcMaterialLayerSet."""
    layers: list[dict[str, Any]] = []
    total = 0.0

    for layer in layer_set.MaterialLayers or []:
        mat_name: str | None = layer.Material.Name if layer.Material else None
        thickness: float = float(layer.LayerThickness or 0.0)
        total += thickness
        layers.append({"material": mat_name, "thickness_m": thickness})

    set_name: str | None = getattr(layer_set, "LayerSetName", None)
    # LayerSetName pode ser None mesmo quando os layers têm nomes
    if not set_name and layers:
        set_name = layers[0]["material"]

    context["material_name"] = set_name
    context["thickness_m"] = total if total > 0.0 else None
    context["layers"] = layers


# ---------------------------------------------------------------------------
# Função auxiliar — extração de IsExternal do elemento
# ---------------------------------------------------------------------------


def _get_is_external(psets: dict[str, dict[str, Any]]) -> bool | None:
    """Retorna o valor de IsExternal do primeiro Pset que o contiver, ou None."""
    for props in psets.values():
        if "IsExternal" in props:
            return props["IsExternal"]
    return None


def _get_load_bearing(psets: dict[str, dict[str, Any]]) -> bool | None:
    """Função estrutural declarada nos Psets do elemento, ou None se ausente.

    Decide ``R`` vs ``EI`` na resistência ao fogo: divisória não portante não
    tem critério de resistência mecânica. O drywall do prédio traz
    ``LoadBearing=False`` e o dado nunca chegava ao prompt.
    """
    for props in psets.values():
        for chave in ("LoadBearing", "IsLoadBearing"):
            valor = props.get(chave)
            if isinstance(valor, bool):
                return valor
    return None


def _get_predefined_type(element: ifcopenshell.entity_instance) -> str | None:
    """PredefinedType do elemento, caindo no tipo quando a instância não define.

    Distingue laje de piso (``FLOOR``) de cobertura (``ROOF``) — sem isso o
    modelo respondia ``LoadBearing=True`` para telha de fibrocimento.
    """
    valor = getattr(element, "PredefinedType", None)
    if valor and str(valor) != "NOTDEFINED":
        return str(valor)
    try:
        tipo = ifcopenshell.util.element.get_type(element)
    except Exception:
        return None
    valor_tipo = getattr(tipo, "PredefinedType", None) if tipo is not None else None
    if valor_tipo and str(valor_tipo) != "NOTDEFINED":
        return str(valor_tipo)
    return str(valor) if valor else None


def _sanitize_psets_for_context(
    psets: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Remove chaves internas do ifcopenshell (ex: 'id') antes de incluir no contexto."""
    return {
        pset_name: {k: v for k, v in props.items() if k != "id"}
        for pset_name, props in psets.items()
    }


# ---------------------------------------------------------------------------
# Diagnóstico principal
# ---------------------------------------------------------------------------


def diagnose_psets(
    ifc_file: ifcopenshell.file,
    required_psets: dict[str, dict[str, list[str]]] | None = None,
) -> list[Issue]:
    """Diagnostica elementos com Psets obrigatórios ausentes ou vazios."""
    if required_psets is None:
        required_psets = DEFAULT_REQUIRED_PSETS

    issues: list[Issue] = []

    for ifc_class, psets_spec in required_psets.items():
        elements = ifc_file.by_type(ifc_class)
        logger.debug(
            f"Verificando {len(elements)} {ifc_class}(s) para Psets obrigatórios"
        )

        for element in elements:
            try:
                _check_element(element, psets_spec, ifc_file, issues)
            except Exception as exc:
                logger.warning(
                    f"Erro inesperado ao verificar {element.GlobalId}: {exc}"
                )

    return issues


def _check_element(
    element: ifcopenshell.entity_instance,
    psets_spec: dict[str, list[str]],
    ifc_file: ifcopenshell.file,
    issues: list[Issue],
) -> None:
    """Verifica um único elemento contra todos os Psets requeridos e acumula Issues."""
    existing_psets = ifcopenshell.util.element.get_psets(element)
    existing_summary = _sanitize_psets_for_context(existing_psets)
    mat_context = _extract_element_material_context(element, ifc_file)
    is_external = _get_is_external(existing_psets)
    load_bearing = _get_load_bearing(existing_psets)
    predefined_type = _get_predefined_type(element)

    element_class = element.is_a()
    short_guid = element.GlobalId[:8]
    element_name: str | None = getattr(element, "Name", None)

    for pset_name, required_props in psets_spec.items():
        pset_data = existing_psets.get(pset_name, {})

        for prop_name in required_props:
            value = pset_data.get(prop_name) if pset_data else None

            if not _is_empty_value(value, prop_name):
                continue

            severity: str = (
                "high" if prop_name in _HIGH_SEVERITY_PROPERTIES else "medium"
            )

            issue_context: dict[str, Any] = {
                "pset_name": pset_name,
                "check_property": prop_name,
                "material_name": mat_context["material_name"],
                "thickness_m": mat_context["thickness_m"],
                # As camadas ja eram extraidas e descartadas aqui: sem elas, o
                # prompt de fogo/termico recebia so o nome do tipo.
                "layers": mat_context["layers"],
                "is_external": is_external,
                # Funcao estrutural decide R vs EI na resistencia ao fogo, e o
                # PredefinedType distingue laje de piso de cobertura — ambos
                # existiam no IFC e nunca chegavam ao modelo.
                "load_bearing": load_bearing,
                "predefined_type": predefined_type,
                "existing_psets": existing_summary,
            }

            # Para IfcSpace.Category, enriquecer com elementos contidos e adjacências
            if element_class == "IfcSpace" and prop_name == "Category":
                try:
                    issue_context["contained_elements"] = _extract_contained_elements(
                        element, ifc_file
                    )
                    adjacent, is_exterior = _extract_adjacent_spaces(element, ifc_file)
                    issue_context["adjacent_spaces"] = adjacent
                    issue_context["is_on_exterior"] = is_exterior
                    qto = ifcopenshell.util.element.get_psets(element, qtos_only=True)
                    base_qto = qto.get("Qto_SpaceBaseQuantities", {})
                    issue_context["area_m2"] = (
                        base_qto.get("NetFloorArea") or base_qto.get("GrossFloorArea") or None
                    )
                except Exception as exc:
                    logger.warning(
                        f"Erro ao enriquecer contexto de Category para {element.GlobalId}: {exc}"
                    )

            issues.append(
                Issue(
                    element_guid=element.GlobalId,
                    element_class=element_class,
                    element_name=element_name,
                    issue_type="pset_missing",
                    severity=severity,  # type: ignore[arg-type]
                    description=f"{element_class} #{short_guid}: {pset_name}.{prop_name} ausente",
                    context=issue_context,
                )
            )
            logger.debug(
                f"Issue pset_missing: {element_class} #{short_guid} — "
                f"{pset_name}.{prop_name} ({severity})"
            )
