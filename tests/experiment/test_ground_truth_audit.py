"""Política local e conservadora para auditar rótulos de ground truth."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from src.experiment.evaluator import GroundTruthItem
from src.experiment.ground_truth_audit import (
    AuditDecision,
    ThermalEvidence,
    audit_legacy_item,
    derive_casa_decision,
)
from src.ifc_analyzer.material_reader import MaterialReading
from src.models import Issue


def _issue(
    *,
    property_name: str = "Category",
    issue_type: str = "pset_missing",
    element_class: str = "IfcSpace",
    element_guid: str = "TARGET-GUID",
    context: dict[str, Any] | None = None,
) -> Issue:
    issue_context = {"check_property": property_name}
    issue_context.update(context or {})
    return Issue(
        element_guid=element_guid,
        element_class=element_class,
        element_name="Elemento de teste",
        issue_type=issue_type,
        severity="medium",
        description="Rótulo ausente",
        context=issue_context,
    )


def _derive(
    issue: Issue,
    *,
    element_type_key: tuple[str, str] = ("IfcWall", "TYPE-GUID"),
    element_type_name: str = "Tipo de teste",
    element_long_name: str | None = None,
    authored_thermal_by_type: dict[tuple[str, str], ThermalEvidence] | None = None,
    material_reading: MaterialReading | None = None,
) -> AuditDecision:
    return derive_casa_decision(
        issue,
        element_type_key=element_type_key,
        element_type_name=element_type_name,
        element_long_name=element_long_name,
        authored_thermal_by_type=authored_thermal_by_type or {},
        material_reading=material_reading or MaterialReading(),
    )


def _assert_item(decision: AuditDecision, expected: Any) -> None:
    assert decision.expected_value == expected
    assert decision.skip_reason is None


def _assert_skipped(decision: AuditDecision) -> None:
    assert decision.expected_value is None
    assert decision.accepted_alternatives == []
    assert decision.skip_reason


def test_audit_decision_requires_exactly_one_item_or_skip():
    """A mutação que aceite um skip vazio junto de um item deve quebrar este teste."""
    with pytest.raises(ValidationError):
        AuditDecision(expected_value="BEDROOM", skip_reason=" ")

    with pytest.raises(ValidationError):
        AuditDecision()


def test_predio_preserves_verified_legacy_item():
    """A mutação que descarte um booleano ratificado deve quebrar este teste."""
    issue = _issue(property_name="LoadBearing", element_class="IfcWall")
    legacy = GroundTruthItem(
        expected_value=False,
        accepted_alternatives=[True],
        verified=True,
        notes="Intencionalidade registrada e revisada pelo autor.",
    )

    decision = audit_legacy_item(issue, legacy)

    _assert_item(decision, False)
    assert decision.accepted_alternatives == [True]
    assert decision.notes is not None
    assert decision.notes.count("não representa desempenho físico medido") == 1


@pytest.mark.parametrize(
    ("element_class", "expected_value", "notes"),
    [
        ("IfcWall", 2.35, "Estimativa preliminar — CONFERIR composição."),
        ("IfcWindow", 5.7, "Referência genérica para vidro simples."),
        ("IfcRoof", 4.6, "Referência genérica para cobertura."),
    ],
)
def test_predio_skips_legacy_item_marked_conferir(element_class, expected_value, notes):
    """A mutação que aceite uma nota ainda incerta deve quebrar este teste."""
    issue = _issue(property_name="ThermalTransmittance", element_class=element_class)
    legacy = GroundTruthItem(
        expected_value=expected_value,
        verified=True,
        notes=notes,
    )

    decision = audit_legacy_item(issue, legacy)

    _assert_skipped(decision)
    assert any(word in decision.skip_reason.lower() for word in ("incerteza", "não ratificada"))


def test_predio_removes_unratified_ei_alternatives():
    """A mutação que retenha a emenda EI pendente deve quebrar este teste."""
    issue = _issue(property_name="FireRating", element_class="IfcWall")
    legacy = GroundTruthItem(
        expected_value="REI 60",
        accepted_alternatives=["REI 90", "REI 120", "EI 60", "EI 90", "EI 120"],
        verified=True,
        notes="Referência de projeto revisada pelo autor.",
    )

    decision = audit_legacy_item(issue, legacy)

    _assert_item(decision, "REI 60")
    assert decision.accepted_alternatives == ["REI 90", "REI 120"]
    assert decision.notes is not None
    assert decision.notes.count("não representa desempenho físico medido") == 1


@pytest.mark.parametrize(
    ("type_key", "evidence_key"),
    [
        (("IfcWall", "TYPE-GUID"), ("IfcWall", "TYPE-GUID")),
        (("IfcWall", ""), ("IfcWall", "Parede externa 20cm")),
    ],
)
def test_casa_propagates_authored_thermal_value_by_exact_type(type_key, evidence_key):
    """A mutação que ignore classe+GUID ou o fallback exato deve quebrar este teste."""
    issue = _issue(property_name="ThermalTransmittance", element_class="IfcWall")
    evidence = ThermalEvidence(
        value=2.35,
        donor_guids=("DONOR-B", "DONOR-A"),
        unit="W/(m²·K)",
        conflicted=False,
    )
    authored = {
        evidence_key: evidence,
        ("IfcSlab", evidence_key[1]): ThermalEvidence(
            value=3.2,
            donor_guids=("WRONG-CLASS",),
            unit="W/(m²·K)",
            conflicted=False,
        ),
    }

    decision = _derive(
        issue,
        element_type_key=type_key,
        element_type_name="Parede externa 20cm",
        authored_thermal_by_type=authored,
    )

    _assert_item(decision, 2.35)
    assert decision.notes is not None
    assert "W/(m²·K)" in decision.notes
    assert "DONOR-A" in decision.notes
    assert "DONOR-B" in decision.notes


def test_casa_does_not_infer_fire_rating_from_minimum_requirement():
    """A mutação que converta exigência normativa em desempenho deve quebrar este teste."""
    issue = _issue(
        property_name="FireRating",
        element_class="IfcWall",
        context={"minimum_requirement": "REI 60"},
    )

    decision = _derive(issue)

    _assert_skipped(decision)
    assert "declaração" in decision.skip_reason.lower()


@pytest.mark.parametrize("property_name", ["LoadBearing", "IsLoadBearing"])
def test_casa_does_not_infer_load_bearing_from_ifc_class(property_name):
    """A mutação que derive função portante da classe IFC deve quebrar este teste."""
    issue = _issue(property_name=property_name, element_class="IfcWallStandardCase")

    decision = _derive(issue)

    _assert_skipped(decision)
    assert "intencionalidade" in decision.skip_reason.lower()


@pytest.mark.parametrize(
    ("long_name", "expected"),
    [
        ("Quarto", "BEDROOM"),
        ("Sala de estar", "LIVING_ROOM"),
        ("Cozinha", "KITCHEN"),
        ("Banheiro", "BATHROOM"),
        ("Lavabo", "WC"),
        ("Circulação", "CIRCULATION"),
        ("Área de serviço", "SERVICE_AREA"),
        ("Escritório", "OFFICE"),
        ("Sala de reunião", "MEETING_ROOM"),
        ("Recepção", "LOBBY"),
        ("Depósito", "STORAGE"),
        ("Varanda", "BALCONY"),
        ("Área técnica", "TECHNICAL_AREA"),
        ("Sala", None),
    ],
)
def test_casa_maps_only_closed_space_categories(long_name, expected):
    """A mutação que invente token ou resolva termo ambíguo deve quebrar este teste."""
    issue = _issue(property_name="Category", element_class="IfcSpace")

    decision = _derive(issue, element_long_name=long_name)

    if expected is None:
        _assert_skipped(decision)
    else:
        _assert_item(decision, expected)


def test_casa_classifies_only_unambiguous_material_system():
    """A mutação que classifique material inespecífico deve quebrar este teste."""
    issue = _issue(property_name="", issue_type="system_unclassified", element_class="IfcWall")
    explicit = MaterialReading(
        material_name="Sistema Drywall",
        layers=[{"name": "Chapa de gesso", "thickness_m": 0.0125}],
        total_thickness_m=0.10,
    )
    ambiguous = MaterialReading(
        material_name="Madeira e vidro",
        layers=[{"name": "Madeira", "thickness_m": 0.02}],
        total_thickness_m=0.08,
    )

    classified = _derive(issue, material_reading=explicit)
    skipped = _derive(issue, material_reading=ambiguous)
    precast = _derive(
        issue,
        element_type_name="Parede de concreto pré-moldado",
        material_reading=MaterialReading(material_name="Concreto pré-moldado"),
    )

    _assert_item(classified, "Drywall / Steel frame")
    _assert_item(precast, "Concreto pré-moldado")
    _assert_skipped(skipped)


def test_casa_maps_garagem_to_garage():
    """A mutação que omita o token GARAGE deve quebrar este teste."""
    issue = _issue(property_name="Category", element_class="IfcSpace")

    decision = _derive(issue, element_long_name="Garagem")

    _assert_item(decision, "GARAGE")


@pytest.mark.parametrize("element_class", ["IfcWall", "IfcSlab"])
def test_generic_concrete_does_not_imply_reinforced_cast_in_place(element_class):
    """A mutação que transforme concreto genérico em sistema específico deve quebrar este teste."""
    issue = _issue(property_name="", issue_type="system_unclassified", element_class=element_class)
    reading = MaterialReading(
        material_name="Concreto",
        layers=[{"name": "Concreto", "thickness_m": 0.12}],
        total_thickness_m=0.12,
    )

    decision = _derive(issue, element_type_name="Tipo concreto", material_reading=reading)

    _assert_skipped(decision)


def test_slab_uses_slab_vocabulary():
    """A mutação que aplique vocabulário de parede a uma laje deve quebrar este teste."""
    issue = _issue(property_name="", issue_type="system_unclassified", element_class="IfcSlab")
    reading = MaterialReading(
        material_name="Piso porcelanato",
        layers=[{"name": "Porcelanato", "thickness_m": 0.01}],
        total_thickness_m=0.01,
    )

    decision = _derive(issue, element_type_name="Piso porcelanato", material_reading=reading)

    _assert_item(decision, "Piso cerâmico / porcelanato")


def test_conflicting_thermal_donors_are_skipped():
    """A mutação que propague doadores discordantes deve quebrar este teste."""
    issue = _issue(property_name="ThermalTransmittance", element_class="IfcWall")
    evidence = ThermalEvidence(
        value=2.35,
        donor_guids=("DONOR-A", "DONOR-B"),
        unit="W/(m²·K)",
        conflicted=True,
    )

    decision = _derive(issue, authored_thermal_by_type={("IfcWall", "TYPE-GUID"): evidence})

    _assert_skipped(decision)
    assert "conflito" in decision.skip_reason.lower()


def test_out_of_scope_property_is_skipped():
    """A mutação que rotule propriedade não auditada deve quebrar este teste."""
    issue = _issue(property_name="Reference", element_class="IfcWall")

    decision = _derive(issue)

    _assert_skipped(decision)
    assert decision.skip_reason == "fora do escopo evidence-audited-v1"
