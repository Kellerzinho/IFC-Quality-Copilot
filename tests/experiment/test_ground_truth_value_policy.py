"""Política determinística que atribui valor concreto a cada diagnóstico."""

from __future__ import annotations

import pytest

from src.experiment.evaluator import GroundTruthItem
from src.experiment.ground_truth_value_policy import (
    ElementEvidence,
    LayerEvidence,
    UnsupportedGroundTruthFamily,
    resolve_ground_truth_decision,
)
from src.models import Issue


def _issue(
    property_name: str,
    *,
    element_class: str = "IfcWall",
    issue_type: str = "pset_missing",
    name: str = "Elemento",
    context: dict[str, object] | None = None,
) -> Issue:
    issue_context: dict[str, object] = {"check_property": property_name}
    issue_context.update(context or {})
    return Issue(
        element_guid="A" * 22,
        element_class=element_class,
        element_name=name,
        issue_type=issue_type,
        severity="high",
        description="valor ausente",
        context=issue_context,
    )


def _resolve(
    issue: Issue,
    evidence: ElementEvidence | None = None,
    *,
    prior_item: GroundTruthItem | None = None,
    equivalent_donor: GroundTruthItem | None = None,
):
    return resolve_ground_truth_decision(
        issue,
        evidence or ElementEvidence(element_class=issue.element_class),
        prior_item=prior_item,
        equivalent_donor=equivalent_donor,
        building_context={
            "building_type": "Residencial multifamiliar",
            "bioclimatic_zone": "4A",
        },
    )


def test_immutable_legacy_item_wins_over_new_alias():
    issue = _issue("LoadBearing")
    prior = GroundTruthItem(
        element_guid=issue.element_guid,
        issue_type=issue.issue_type,
        check_property="LoadBearing",
        issue_id=issue.id,
        expected_value=True,
        accepted_alternatives=[],
        verified=True,
        notes="Valor ratificado.",
        legacy_reference=True,
    )

    decision = _resolve(
        issue,
        ElementEvidence(element_class="IfcWall", load_bearing_alias=False),
        prior_item=prior,
    )

    assert decision.expected_value is True
    assert decision.source_kind == "existing_gt"
    assert decision.confidence == "high"
    assert decision.legacy_reference is True


def test_exact_equivalent_donor_is_reused_with_high_confidence():
    issue = _issue("FireRating", element_class="IfcDoor")
    donor = GroundTruthItem(
        expected_value="EI 90",
        accepted_alternatives=[],
        verified=True,
        notes="Doador da mesma equivalência.",
    )

    decision = _resolve(issue, equivalent_donor=donor)

    assert decision.expected_value == "EI 90"
    assert decision.source_kind == "equivalent_donor"
    assert decision.confidence == "high"


@pytest.mark.parametrize("property_name", ["LoadBearing", "IsLoadBearing"])
def test_load_bearing_uses_ifc_boolean_alias(property_name: str):
    issue = _issue(property_name)

    decision = _resolve(
        issue,
        ElementEvidence(element_class="IfcWall", load_bearing_alias=False),
    )

    assert decision.expected_value is False
    assert decision.source_kind == "ifc_alias"
    assert decision.confidence == "high"


def test_category_uses_long_name_alias():
    issue = _issue("Category", element_class="IfcSpace")

    decision = _resolve(
        issue,
        ElementEvidence(element_class="IfcSpace", element_long_name="Cozinha"),
    )

    assert decision.expected_value == "KITCHEN"
    assert decision.source_kind == "ifc_alias"


def test_category_without_hint_gets_explicit_probable_value():
    issue = _issue("Category", element_class="IfcSpace")

    decision = _resolve(issue)

    assert decision.expected_value == "TECHNICAL_AREA"
    assert decision.confidence == "low"
    assert decision.source_kind == "probable"
    assert decision.notes.startswith("Hipótese congelada:")


@pytest.mark.parametrize(
    ("element_class", "material", "expected"),
    [
        ("IfcWall", "bloco cerâmico", "Alvenaria de vedação em bloco cerâmico"),
        ("IfcWall", "drywall com chapa de gesso", "Drywall / Steel frame"),
        ("IfcSlab", "piso porcelanato", "Piso cerâmico / porcelanato"),
        ("IfcSlab", "concreto armado", "Laje maciça de concreto armado"),
    ],
)
def test_system_uses_material_vocabulary(element_class: str, material: str, expected: str):
    issue = _issue("", element_class=element_class, issue_type="system_unclassified")

    decision = _resolve(
        issue,
        ElementEvidence(element_class=element_class, material_name=material),
    )

    assert decision.expected_value == expected
    assert decision.confidence == "medium"
    assert decision.source_kind == "typology"


@pytest.mark.parametrize(
    ("element_class", "expected"),
    [
        ("IfcDoor", "IfcRelFillsElement"),
        ("IfcWindow", "IfcRelFillsElement"),
        ("IfcSpace", "IfcRelSpaceBoundary"),
    ],
)
def test_relation_has_concrete_ifc_target(element_class: str, expected: str):
    issue = _issue("", element_class=element_class, issue_type="relation_broken")

    decision = _resolve(issue)

    assert decision.expected_value == expected
    assert decision.source_kind == "typology"


def test_literal_expected_relation_has_priority():
    issue = _issue("", element_class="IfcDoor", issue_type="relation_broken")

    decision = _resolve(
        issue,
        ElementEvidence(
            element_class="IfcDoor",
            expected_relation="IfcRelConnectsElements",
        ),
    )

    assert decision.expected_value == "IfcRelConnectsElements"
    assert decision.source_kind == "ifc_literal"
    assert decision.confidence == "high"


def test_relation_does_not_require_synthetic_check_property():
    issue = _issue("", element_class="IfcDoor", issue_type="relation_broken")
    issue.context = {"expected_relation": "IfcRelFillsElement"}

    decision = _resolve(
        issue,
        ElementEvidence(
            element_class="IfcDoor",
            expected_relation="IfcRelFillsElement",
        ),
    )

    assert decision.expected_value == "IfcRelFillsElement"
    assert decision.source_kind == "ifc_literal"


def test_thermal_transmittance_is_calculated_from_complete_layers():
    issue = _issue("ThermalTransmittance")
    evidence = ElementEvidence(
        element_class="IfcWall",
        layers=(
            LayerEvidence(material="argamassa", thickness_m=0.02),
            LayerEvidence(material="concreto", thickness_m=0.10),
            LayerEvidence(material="argamassa", thickness_m=0.02),
        ),
    )

    decision = _resolve(issue, evidence)

    assert decision.expected_value == 3.82
    assert decision.source_kind == "calculation"
    assert decision.confidence == "medium"
    assert "Rsi=0.13" in decision.notes
    assert "W/(m²·K)" in decision.notes


@pytest.mark.parametrize(
    ("element_class", "expected"),
    [
        ("IfcWall", 2.48),
        ("IfcSlab", 3.20),
        ("IfcRoof", 2.00),
        ("IfcDoor", 3.00),
        ("IfcWindow", 5.70),
        ("IfcCurtainWall", 5.70),
    ],
)
def test_thermal_fallback_is_concrete_for_supported_class(
    element_class: str,
    expected: float,
):
    issue = _issue("ThermalTransmittance", element_class=element_class)

    decision = _resolve(issue)

    assert decision.expected_value == expected
    assert decision.source_kind == "probable"
    assert decision.confidence == "low"
    assert "W/(m²·K)" in decision.notes


@pytest.mark.parametrize(
    ("element_class", "expected"),
    [("IfcDoor", "EI 60"), ("IfcWindow", "EI 60"), ("IfcWall", "REI 60")],
)
def test_fire_rating_has_canonical_probable_fallback(element_class: str, expected: str):
    issue = _issue("FireRating", element_class=element_class)

    decision = _resolve(issue)

    assert decision.expected_value == expected
    assert decision.confidence == "low"
    assert decision.notes.startswith("Hipótese congelada:")


@pytest.mark.parametrize(
    ("element_class", "expected"),
    [
        ("IfcWall", "Rw 40 dB"),
        ("IfcSlab", "Rw 45 dB"),
        ("IfcDoor", "Rw 25 dB"),
        ("IfcWindow", "Rw 30 dB"),
    ],
)
def test_acoustic_rating_has_canonical_typology(element_class: str, expected: str):
    issue = _issue("AcousticRating", element_class=element_class)

    decision = _resolve(issue)

    assert decision.expected_value == expected
    assert decision.source_kind == "typology"
    assert decision.confidence == "medium"


def test_generic_clear_glass_has_frozen_shgc():
    issue = _issue("SolarHeatGainCoefficient", element_class="IfcWindow")

    decision = _resolve(
        issue,
        ElementEvidence(element_class="IfcWindow", material_name="vidro incolor"),
    )

    assert decision.expected_value == 0.87
    assert decision.source_kind == "typology"
    assert decision.confidence == "medium"


@pytest.mark.parametrize(
    ("name", "is_external", "expected"),
    [
        ("Escada externa", True, True),
        ("Patamar interno", False, True),
        ("Piso sala seca", False, False),
    ],
)
def test_non_skid_surface_uses_function_and_location(
    name: str,
    is_external: bool,
    expected: bool,
):
    issue = _issue("HasNonSkidSurface", element_class="IfcStair", name=name)

    decision = _resolve(
        issue,
        ElementEvidence(element_class="IfcStair", is_external=is_external),
    )

    assert decision.expected_value is expected


def test_unknown_family_fails_instead_of_returning_sentinel():
    issue = _issue("Reference", element_class="IfcWall")

    with pytest.raises(UnsupportedGroundTruthFamily, match="Reference"):
        _resolve(issue)
