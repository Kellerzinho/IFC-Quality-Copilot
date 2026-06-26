"""Resolução flexível de propriedades IFC com suporte a aliases e busca global.

Elimina falsos positivos causados por nomes de Pset não-padrão ou nomes de
propriedade alternativos comuns em modelos exportados por diferentes ferramentas.

Estratégia de busca (em ordem de prioridade):
  1. Pset exato + propriedade exata   (comportamento original)
  2. Pset exato + alias da propriedade
  3. Qualquer Pset + propriedade exata
  4. Qualquer Pset + alias da propriedade
"""

from typing import Any

import ifcopenshell
import ifcopenshell.util.element
from loguru import logger

# ---------------------------------------------------------------------------
# Aliases de propriedade: nomes alternativos que ferramentas BIM usam para a
# mesma propriedade IFC canônica. Chave = nome canônico IFC.
# ---------------------------------------------------------------------------

PROPERTY_ALIASES: dict[str, list[str]] = {
    "ThermalTransmittance": [
        "U_Value", "U-Value", "UValue", "Uwert",
        "TransmittanceThermique", "U_Wert", "Uvalue",
        "HeatTransferCoefficient", "OverallHeatTransferCoefficient",
    ],
    "SolarHeatGainCoefficient": [
        "SHGC", "g_value", "g-value", "gValue",
        "SolarFactor", "FatorSolar", "g_Wert",
        "SolarTransmittance", "TotalSolarEnergyTransmittance",
    ],
    "VisibleTransmittance": [
        "LightTransmittance", "VisibleLightTransmittance",
        "TransmittanceLumineuse", "Tv", "VLT",
    ],
    "FireRating": [
        "TRRF", "FireResistance", "REI", "REI_Value",
        "FireResistanceRating", "ClassificationFire",
        "EI", "EI_Value", "R_Value",
    ],
    "AcousticRating": [
        "SoundInsulation", "Rw", "DnTw", "SoundReduction",
        "SoundInsulationIndex", "WeightedSoundReduction",
        "AcousticPerformance", "Rw_Value",
    ],
    "SoundTransmissionLoss": [
        "STC", "STCRating", "SoundTransmissionClass",
        "AcousticInsulation",
    ],
    "IsExternal": [
        "External", "IsOutside", "ExternalFace",
        "ExtWall", "IsExterior",
    ],
    "IsLoadBearing": [
        "LoadBearing", "Structural", "IsStructural",
        "StructuralElement", "PorteurDeCharge",
    ],
    "LoadBearing": [
        "IsLoadBearing", "Structural", "IsStructural",
        "PorteurDeCharge",
    ],
    "ThermalConductivity": [
        "LambdaValue", "Lambda", "ThermalCond",
        "ConductiviteThermique", "Waermeleitfaehigkeit",
    ],
    "CompressiveStrength": [
        "Fck", "ConcreteStrength", "CharacteristicStrength",
        "DesignStrength", "fcd",
    ],
}

# Inverso: alias → nome canônico (para normalização de resultados)
_ALIAS_TO_CANONICAL: dict[str, str] = {
    alias: canonical
    for canonical, aliases in PROPERTY_ALIASES.items()
    for alias in aliases
}


def resolve_property(
    element: ifcopenshell.entity_instance,
    required_pset: str,
    required_prop: str,
    psets_cache: dict[str, dict[str, dict]] | None = None,
) -> tuple[Any, str | None, str | None, bool]:
    """Busca uma propriedade IFC com fallback para aliases e Psets alternativos.

    Retorna (value, found_pset, found_prop, is_exact_match).

    - value: valor encontrado, ou None se não encontrado em nenhuma fonte
    - found_pset: Pset onde o valor foi encontrado, ou None
    - found_prop: nome da propriedade como encontrada, ou None
    - is_exact_match: True se encontrada no Pset e nome exatos do IDS

    Estratégia de busca:
        1. Pset exato + prop exata   (exact match)
        2. Pset exato + alias da prop
        3. Qualquer Pset + prop exata
        4. Qualquer Pset + alias da prop
    """
    psets = _get_psets_cached(element, psets_cache)
    prop_aliases = PROPERTY_ALIASES.get(required_prop, [])

    # ---- Etapa 1: exato ------------------------------------------------
    pset_data = psets.get(required_pset, {})
    value = pset_data.get(required_prop)
    if value is not None:
        return value, required_pset, required_prop, True

    # ---- Etapa 2: alias no Pset exato ----------------------------------
    for alias in prop_aliases:
        value = pset_data.get(alias)
        if value is not None:
            logger.debug(
                "Propriedade '{}' encontrada como alias '{}' no Pset '{}' (elem {})",
                required_prop, alias, required_pset, element.GlobalId[:8],
            )
            return value, required_pset, alias, False

    # ---- Etapa 3: prop exata em qualquer Pset --------------------------
    for pset_name, props in psets.items():
        if pset_name == required_pset:
            continue
        value = props.get(required_prop)
        if value is not None:
            logger.debug(
                "Propriedade '{}' encontrada no Pset alternativo '{}' (elem {})",
                required_prop, pset_name, element.GlobalId[:8],
            )
            return value, pset_name, required_prop, False

    # ---- Etapa 4: alias em qualquer Pset --------------------------------
    for alias in prop_aliases:
        for pset_name, props in psets.items():
            value = props.get(alias)
            if value is not None:
                logger.debug(
                    "Propriedade '{}' encontrada como alias '{}' no Pset '{}' (elem {})",
                    required_prop, alias, pset_name, element.GlobalId[:8],
                )
                return value, pset_name, alias, False

    return None, None, None, False


def find_all_occurrences(
    element: ifcopenshell.entity_instance,
    prop_name: str,
    psets_cache: dict[str, dict[str, dict]] | None = None,
) -> list[tuple[str, str, Any]]:
    """Retorna todas as ocorrências de uma propriedade (por nome exato ou alias) no elemento.

    Retorna lista de (pset_name, found_prop_name, value) para todos os Psets
    onde a propriedade ou um de seus aliases foi encontrado.
    """
    psets = _get_psets_cached(element, psets_cache)
    aliases = {prop_name} | set(PROPERTY_ALIASES.get(prop_name, []))
    # Também resolve se o nome for um alias → encontra o canonical + aliases do canonical
    canonical = _ALIAS_TO_CANONICAL.get(prop_name)
    if canonical:
        aliases.add(canonical)
        aliases.update(PROPERTY_ALIASES.get(canonical, []))

    results: list[tuple[str, str, Any]] = []
    for pset_name, props in psets.items():
        for alias in aliases:
            value = props.get(alias)
            if value is not None:
                results.append((pset_name, alias, value))

    return results


def normalize_canonical(prop_name: str) -> str:
    """Retorna o nome canônico IFC para uma propriedade, resolvendo aliases."""
    return _ALIAS_TO_CANONICAL.get(prop_name, prop_name)


def _get_psets_cached(
    element: ifcopenshell.entity_instance,
    psets_cache: dict[str, dict[str, dict]] | None,
) -> dict[str, dict]:
    if psets_cache is not None:
        guid = getattr(element, "GlobalId", None)
        if guid is not None:
            cached = psets_cache.get(guid)
            if cached is not None:
                return cached
            try:
                result = ifcopenshell.util.element.get_psets(element)
            except Exception:
                result = {}
            psets_cache[guid] = result
            return result

    try:
        return ifcopenshell.util.element.get_psets(element)
    except Exception:
        return {}
