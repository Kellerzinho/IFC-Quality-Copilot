"""Resolvedor determinístico dos valores do ground truth de cobertura integral."""

from __future__ import annotations

import math
import unicodedata
from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict

from src.experiment.evaluator import GroundTruthItem
from src.experiment.ground_truth_policy import GroundTruthDecision
from src.models import Issue

THERMAL_FALLBACK = {
    "IfcWall": 2.48,
    "IfcWallStandardCase": 2.48,
    "IfcSlab": 3.20,
    "IfcSlabStandardCase": 3.20,
    "IfcRoof": 2.00,
    "IfcDoor": 3.00,
    "IfcWindow": 5.70,
    "IfcCurtainWall": 5.70,
}
ACOUSTIC_FALLBACK_DB = {
    "IfcWall": 40,
    "IfcWallStandardCase": 40,
    "IfcSlab": 45,
    "IfcSlabStandardCase": 45,
    "IfcRoof": 40,
    "IfcDoor": 25,
    "IfcWindow": 30,
}
FIRE_FALLBACK = {"IfcDoor": "EI 60", "IfcWindow": "EI 60"}
FIRE_FALLBACK_DEFAULT = "REI 60"
SHGC_GENERIC_CLEAR_GLASS = 0.87

_CATEGORY_ALIASES = {
    "quarto": "BEDROOM",
    "dormitorio": "BEDROOM",
    "sala de estar": "LIVING_ROOM",
    "sala": "LIVING_ROOM",
    "cozinha": "KITCHEN",
    "banheiro": "BATHROOM",
    "lavabo": "WC",
    "wc": "WC",
    "circulacao": "CIRCULATION",
    "corredor": "CIRCULATION",
    "area de servico": "SERVICE_AREA",
    "escritorio": "OFFICE",
    "sala de reuniao": "MEETING_ROOM",
    "recepcao": "LOBBY",
    "deposito": "STORAGE",
    "varanda": "BALCONY",
    "sacada": "BALCONY",
    "garagem": "GARAGE",
    "area tecnica": "TECHNICAL_AREA",
}
_LAMBDA_BY_TOKEN = {
    "concreto": 1.75,
    "argamassa": 1.15,
    "revestimento cimenticio": 1.15,
    "ceramica": 0.90,
    "ceramico": 0.90,
    "gesso": 0.35,
    "eps": 0.04,
    "madeira": 0.15,
    "vidro": 1.00,
}


class UnsupportedGroundTruthFamily(ValueError):
    """Indica uma família sem regra concreta aprovada."""


class LayerEvidence(BaseModel):
    """Camada material normalizada para cálculo térmico."""

    model_config = ConfigDict(extra="forbid")

    material: str
    thickness_m: float | None = None


class ElementEvidence(BaseModel):
    """Evidência IFC necessária para decidir sem abrir o modelo no resolvedor."""

    model_config = ConfigDict(extra="forbid")

    element_class: str
    element_type_name: str = ""
    element_long_name: str = ""
    material_name: str = ""
    layers: tuple[LayerEvidence, ...] = ()
    total_thickness_m: float | None = None
    is_external: bool | None = None
    load_bearing_alias: bool | None = None
    expected_relation: str | None = None


def _normalise(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    without_accents = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(without_accents.casefold().replace("_", " ").split())


def _decision(
    expected_value: object,
    confidence: str,
    source_kind: str,
    notes: str,
    *,
    alternatives: list[object] | None = None,
    legacy_reference: bool = False,
) -> GroundTruthDecision:
    return GroundTruthDecision(
        expected_value=expected_value,
        accepted_alternatives=list(alternatives or []),
        confidence=confidence,
        source_kind=source_kind,
        notes=notes,
        legacy_reference=legacy_reference,
    )


def _frozen_item_decision(
    item: GroundTruthItem,
    *,
    source_kind: str,
    legacy_reference: bool,
) -> GroundTruthDecision:
    if not item.verified or item.expected_value is None:
        raise ValueError("frozen donor must be verified and concrete")
    return _decision(
        item.expected_value,
        "high",
        source_kind,
        item.notes or "Referência congelada e identificada pela mesma equivalência.",
        alternatives=list(item.accepted_alternatives),
        legacy_reference=legacy_reference,
    )


def _thermal_surface_resistance(element_class: str) -> tuple[float, float, str]:
    if element_class in {"IfcRoof"}:
        return 0.10, 0.04, "fluxo ascendente"
    if element_class in {"IfcSlab", "IfcSlabStandardCase"}:
        return 0.17, 0.04, "fluxo descendente"
    return 0.13, 0.04, "fluxo horizontal"


def _lambda_for(material: str) -> float | None:
    normalised = _normalise(material)
    for token, value in _LAMBDA_BY_TOKEN.items():
        if token in normalised:
            return value
    return None


def _thermal_decision(issue: Issue, evidence: ElementEvidence) -> GroundTruthDecision:
    layer_terms: list[tuple[LayerEvidence, float]] = []
    for layer in evidence.layers:
        conductivity = _lambda_for(layer.material)
        if (
            conductivity is None
            or layer.thickness_m is None
            or isinstance(layer.thickness_m, bool)
            or not math.isfinite(layer.thickness_m)
            or layer.thickness_m <= 0
        ):
            layer_terms = []
            break
        layer_terms.append((layer, conductivity))

    if layer_terms:
        rsi, rse, flow = _thermal_surface_resistance(issue.element_class)
        layer_resistance = 0.0
        for layer, conductivity in layer_terms:
            thickness = layer.thickness_m
            if thickness is None:
                raise AssertionError("validated thermal layer lost its thickness")
            layer_resistance += thickness / conductivity
        r_total = rsi + layer_resistance + rse
        value = round(1.0 / r_total, 2)
        layer_note = "; ".join(
            f"{layer.material}={layer.thickness_m:.4f}/{conductivity:.2f}"
            for layer, conductivity in layer_terms
            if layer.thickness_m is not None
        )
        return _decision(
            value,
            "medium",
            "calculation",
            (
                f"Cálculo U=1/Rt ({flow}); Rsi={rsi:.2f}; {layer_note}; "
                f"Rse={rse:.2f}; Rt={r_total:.4f} m²·K/W."
            ),
        )

    fallback = THERMAL_FALLBACK.get(issue.element_class)
    if fallback is None:
        raise UnsupportedGroundTruthFamily(
            f"ThermalTransmittance sem regra para {issue.element_class}"
        )
    material_hint = _normalise(
        " ".join(
            [
                evidence.material_name,
                evidence.element_type_name,
                *(layer.material for layer in evidence.layers),
            ]
        )
    )
    if material_hint:
        return _decision(
            fallback,
            "medium",
            "typology",
            (
                "Referência tipológica congelada por classe/material; composição "
                f"insuficiente para cálculo integral: {material_hint}."
            ),
        )
    return _decision(
        fallback,
        "low",
        "probable",
        (
            "Hipótese congelada: transmitância mais provável para "
            f"{issue.element_class}; camadas, espessuras ou λ não foram declarados no IFC."
        ),
    )


def _category_decision(evidence: ElementEvidence) -> GroundTruthDecision:
    hint = _normalise(evidence.element_long_name or evidence.element_type_name)
    if hint:
        for alias, category in sorted(_CATEGORY_ALIASES.items(), key=lambda item: -len(item[0])):
            if alias in hint:
                return _decision(
                    category,
                    "high",
                    "ifc_alias",
                    f"Category derivada do nome IFC: {hint}.",
                )
    return _decision(
        "TECHNICAL_AREA",
        "low",
        "probable",
        (
            "Hipótese congelada: espaço sem nome funcional inequívoco; "
            "TECHNICAL_AREA é o rótulo conservador adotado para o benchmark."
        ),
    )


def _system_decision(issue: Issue, evidence: ElementEvidence) -> GroundTruthDecision:
    hint = _normalise(
        " ".join(
            [
                evidence.material_name,
                evidence.element_type_name,
                evidence.element_long_name,
                *(layer.material for layer in evidence.layers),
            ]
        )
    )
    if issue.element_class in {"IfcWall", "IfcWallStandardCase"}:
        if "drywall" in hint or "chapa de gesso" in hint or "steel frame" in hint:
            value = "Drywall / Steel frame"
        elif "concreto pre" in hint:
            value = "Concreto pré-moldado"
        elif "concreto" in hint and "bloco" in hint:
            value = "Alvenaria em bloco de concreto"
        elif "concreto armado" in hint:
            value = "Concreto armado moldado in loco"
        elif "eps" in hint:
            value = "Painel de EPS"
        elif "bloco ceram" in hint or "alvenaria" in hint:
            value = "Alvenaria de vedação em bloco cerâmico"
        else:
            return _decision(
                "Alvenaria de vedação em bloco cerâmico",
                "low",
                "probable",
                (
                    "Hipótese congelada: parede sem sistema inequívoco; foi adotada a "
                    "tipologia residencial mais provável em Deodoro/RJ."
                ),
            )
    elif issue.element_class in {"IfcSlab", "IfcSlabStandardCase"}:
        if any(token in hint for token in ("porcelanato", "ceramic")):
            value = "Piso cerâmico / porcelanato"
        elif "madeira" in hint:
            value = "Piso de madeira (parquet / taco / deck)"
        elif "grama" in hint:
            value = "Grama natural ou artificial"
        else:
            value = "Laje maciça de concreto armado"
    else:
        raise UnsupportedGroundTruthFamily(
            f"system_unclassified sem vocabulário para {issue.element_class}"
        )
    return _decision(
        value,
        "medium",
        "typology",
        f"Sistema classificado por classe e evidência material congelada: {hint or 'classe IFC'}.",
    )


def _relation_decision(issue: Issue, evidence: ElementEvidence) -> GroundTruthDecision:
    if evidence.expected_relation:
        return _decision(
            evidence.expected_relation,
            "high",
            "ifc_literal",
            "Relação esperada declarada literalmente no diagnóstico IFC.",
        )
    if issue.element_class in {"IfcDoor", "IfcWindow"}:
        relation = "IfcRelFillsElement"
    elif issue.element_class == "IfcSpace":
        relation = "IfcRelSpaceBoundary"
    else:
        raise UnsupportedGroundTruthFamily(f"relation_broken sem regra para {issue.element_class}")
    return _decision(
        relation,
        "medium",
        "typology",
        f"Relação IFC esperada pela função de {issue.element_class}.",
    )


def resolve_ground_truth_decision(
    issue: Issue,
    evidence: ElementEvidence,
    *,
    prior_item: GroundTruthItem | None,
    equivalent_donor: GroundTruthItem | None,
    building_context: Mapping[str, str],
) -> GroundTruthDecision:
    """Aplica a hierarquia aprovada e sempre retorna um valor concreto."""
    del building_context  # o contexto fica explícito na API e nas futuras regras normativas.
    if evidence.element_class != issue.element_class:
        raise ValueError("element evidence class diverges from issue")
    if prior_item is not None and prior_item.legacy_reference:
        return _frozen_item_decision(
            prior_item,
            source_kind="existing_gt",
            legacy_reference=True,
        )
    if equivalent_donor is not None:
        return _frozen_item_decision(
            equivalent_donor,
            source_kind="equivalent_donor",
            legacy_reference=False,
        )
    if issue.issue_type == "relation_broken":
        return _relation_decision(issue, evidence)

    property_name = issue.context.get("check_property")
    if not isinstance(property_name, str):
        raise UnsupportedGroundTruthFamily("check_property ausente ou não textual")

    if property_name in {"LoadBearing", "IsLoadBearing"}:
        if evidence.load_bearing_alias is not None:
            return _decision(
                evidence.load_bearing_alias,
                "high",
                "ifc_alias",
                f"Alias IFC LoadBearing={str(evidence.load_bearing_alias).lower()}.",
            )
        structural = issue.element_class in {"IfcBeam", "IfcColumn", "IfcFooting", "IfcPile"}
        return _decision(
            structural,
            "low",
            "probable",
            (
                "Hipótese congelada: função portante inferida apenas da classe IFC; "
                "não há alias LoadBearing declarado."
            ),
        )
    if property_name == "IsExternal":
        if evidence.is_external is not None:
            return _decision(
                evidence.is_external,
                "high",
                "ifc_alias",
                f"Alias IFC IsExternal={str(evidence.is_external).lower()}.",
            )
        return _decision(
            False,
            "low",
            "probable",
            "Hipótese congelada: elemento tratado como interno sem indicador IFC de exterioridade.",
        )
    if property_name == "Category" and issue.element_class == "IfcSpace":
        return _category_decision(evidence)
    if issue.issue_type == "system_unclassified" and property_name == "":
        return _system_decision(issue, evidence)
    if property_name == "ThermalTransmittance":
        return _thermal_decision(issue, evidence)
    if property_name == "FireRating":
        value = FIRE_FALLBACK.get(issue.element_class, FIRE_FALLBACK_DEFAULT)
        return _decision(
            value,
            "low",
            "probable",
            (
                "Hipótese congelada: classe de resistência ao fogo mais provável para "
                f"{issue.element_class} residencial; função, ensaio e especificação "
                "completos ausentes."
            ),
        )
    if property_name == "AcousticRating":
        rating = ACOUSTIC_FALLBACK_DB.get(issue.element_class)
        if rating is None:
            raise UnsupportedGroundTruthFamily(
                f"AcousticRating sem regra para {issue.element_class}"
            )
        return _decision(
            f"Rw {rating} dB",
            "medium",
            "typology",
            (
                "Referência tipológica congelada de isolamento aéreo por classe de elemento; "
                "não representa ensaio do sistema construído."
            ),
        )
    if property_name == "SolarHeatGainCoefficient":
        hint = _normalise(
            " ".join([evidence.material_name, evidence.element_type_name, issue.element_name or ""])
        )
        if "vidro" in hint or "glass" in hint:
            return _decision(
                SHGC_GENERIC_CLEAR_GLASS,
                "medium",
                "typology",
                "Referência tipológica congelada para vidro incolor comum.",
            )
        return _decision(
            SHGC_GENERIC_CLEAR_GLASS,
            "low",
            "probable",
            (
                "Hipótese congelada: adotado vidro incolor comum (SHGC=0.87); "
                "produto, película e composição não foram declarados no IFC."
            ),
        )
    if property_name == "HasNonSkidSurface":
        hint = _normalise(
            " ".join(
                [
                    issue.element_name or "",
                    evidence.element_type_name,
                    evidence.element_long_name,
                    evidence.material_name,
                ]
            )
        )
        positive = bool(evidence.is_external) or any(
            token in hint
            for token in ("escada", "stair", "patamar", "molhad", "banheiro", "extern")
        )
        return _decision(
            positive,
            "medium",
            "typology",
            (
                "Hipótese funcional congelada a partir de localização/material: "
                f"{hint or 'sem pista'}."
            ),
        )

    raise UnsupportedGroundTruthFamily(
        f"{issue.issue_type}/{property_name or '<empty>'}/{issue.element_class}"
    )
