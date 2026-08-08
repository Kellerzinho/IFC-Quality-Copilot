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

_RATIFIED_LEGACY_SHA256 = "d08d2c7466a71c0cde467a959ed2aebfd4857d1da64944e4504f8f97d4edd6f6"


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


def _legacy_item(issue: Issue, **values: Any) -> GroundTruthItem:
    return GroundTruthItem(
        element_guid=issue.element_guid,
        issue_type=issue.issue_type,
        check_property=issue.context["check_property"],
        issue_id=issue.id,
        **values,
    )


def _audit_legacy(
    issue: Issue,
    legacy: GroundTruthItem,
    *,
    source_sha256: str | None = _RATIFIED_LEGACY_SHA256,
) -> AuditDecision:
    return audit_legacy_item(issue, legacy, source_sha256=source_sha256)


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
    legacy = _legacy_item(
        issue,
        expected_value=False,
        accepted_alternatives=[True],
        verified=True,
        notes="Intencionalidade registrada e revisada pelo autor.",
    )

    decision = _audit_legacy(issue, legacy)

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
    legacy = _legacy_item(
        issue,
        expected_value=expected_value,
        verified=True,
        notes=notes,
    )

    decision = _audit_legacy(issue, legacy)

    _assert_skipped(decision)
    assert any(word in decision.skip_reason.lower() for word in ("incerteza", "não ratificada"))


def test_predio_removes_unratified_ei_alternatives():
    """A mutação que retenha a emenda EI pendente deve quebrar este teste."""
    issue = _issue(property_name="FireRating", element_class="IfcWall")
    legacy = _legacy_item(
        issue,
        expected_value="REI 60",
        accepted_alternatives=["REI 90", "REI 120", "EI 60", "EI 90", "EI 120"],
        verified=True,
        notes="Referência de projeto revisada pelo autor.",
    )

    decision = _audit_legacy(issue, legacy)

    _assert_item(decision, "REI 60")
    assert decision.accepted_alternatives == ["REI 90", "REI 120"]
    assert decision.notes is not None
    assert decision.notes.count("não representa desempenho físico medido") == 1


@pytest.mark.parametrize("source_sha256", ["0" * 64, None])
def test_predio_rejects_legacy_item_without_ratified_snapshot_proof(source_sha256):
    """A mutação que aceite valor sem prova do snapshot congelado deve quebrar este teste."""
    issue = _issue(property_name="Category", element_class="IfcSpace")
    legacy = _legacy_item(issue, expected_value="BEDROOM", verified=True, notes="Revisado.")

    decision = _audit_legacy(issue, legacy, source_sha256=source_sha256)

    _assert_skipped(decision)
    assert "snapshot" in decision.skip_reason.lower()


@pytest.mark.parametrize(
    ("overrides", "reason_fragment"),
    [
        ({"element_guid": "OTHER-GUID"}, "chave natural"),
        ({"issue_id": "other-issue-id"}, "issue_id"),
    ],
)
def test_predio_rejects_legacy_identity_mismatch(overrides, reason_fragment):
    """A mutação que desvincule item legado da issue literal deve quebrar este teste."""
    issue = _issue(property_name="Category", element_class="IfcSpace")
    values = {
        "element_guid": issue.element_guid,
        "issue_type": issue.issue_type,
        "check_property": issue.context["check_property"],
        "issue_id": issue.id,
        "expected_value": "BEDROOM",
        "verified": True,
        "notes": "Revisado.",
    }
    values.update(overrides)
    legacy = GroundTruthItem(**values)

    decision = _audit_legacy(issue, legacy)

    _assert_skipped(decision)
    assert reason_fragment in decision.skip_reason.lower()


def test_predio_rejects_missing_check_property_for_system_item():
    """A mutação que converta campo ausente em vazio literal deve quebrar este teste."""
    issue = _issue(property_name="", issue_type="system_unclassified", element_class="IfcWall")
    issue.context = {}
    legacy = GroundTruthItem(
        element_guid=issue.element_guid,
        issue_type=issue.issue_type,
        check_property="",
        issue_id=issue.id,
        expected_value="Drywall / Steel frame",
        verified=True,
        notes="Revisado.",
    )

    decision = _audit_legacy(issue, legacy)

    _assert_skipped(decision)
    assert "check_property" in decision.skip_reason


@pytest.mark.parametrize("invalid_property", [None, False])
def test_casa_requires_literal_empty_check_property_for_system(invalid_property):
    """A mutação que coaja None/bool para vazio deve quebrar este teste."""
    issue = _issue(
        property_name=invalid_property,
        issue_type="system_unclassified",
        element_class="IfcWall",
    )
    reading = MaterialReading(material_name="Sistema Drywall")

    decision = _derive(issue, material_reading=reading)

    _assert_skipped(decision)
    assert decision.skip_reason == "fora do escopo evidence-audited-v1"


@pytest.mark.parametrize(
    "property_name",
    ["ThermalTransmittance", "FireRating", "LoadBearing", "Category"],
)
def test_casa_routes_known_properties_only_for_pset_missing(property_name):
    """A mutação que roteie relation_broken como propriedade ausente deve quebrar este teste."""
    issue = _issue(
        property_name=property_name,
        issue_type="relation_broken",
        element_class="IfcSpace" if property_name == "Category" else "IfcWall",
    )
    authored = {
        ("IfcWall", "TYPE-GUID"): ThermalEvidence(
            value=2.35,
            donor_guids=("DONOR-A",),
            unit="W/(m²·K)",
            conflicted=False,
        )
    }

    decision = _derive(issue, element_long_name="Quarto", authored_thermal_by_type=authored)

    _assert_skipped(decision)
    assert decision.skip_reason == "fora do escopo evidence-audited-v1"


def test_casa_rejects_absent_check_property_for_system():
    """A mutação que trate campo ausente como vazio literal deve quebrar este teste."""
    issue = _issue(property_name="", issue_type="system_unclassified", element_class="IfcWall")
    issue.context = {}

    decision = _derive(issue, material_reading=MaterialReading(material_name="Sistema Drywall"))

    _assert_skipped(decision)
    assert decision.skip_reason == "fora do escopo evidence-audited-v1"


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


@pytest.mark.parametrize(
    ("element_type_name", "material_name"),
    [
        ("Parede sem drywall", "Sistema Drywall"),
        ("Bloco cerâmico não estrutural", "Bloco cerâmico"),
        ("Concreto armado não moldado in loco", "Concreto armado"),
    ],
)
def test_casa_skips_negated_or_contradictory_material_system(
    element_type_name,
    material_name,
):
    """A mutação que trate negação como evidência positiva deve quebrar este teste."""
    issue = _issue(property_name="", issue_type="system_unclassified", element_class="IfcWall")

    decision = _derive(
        issue,
        element_type_name=element_type_name,
        material_reading=MaterialReading(material_name=material_name),
    )

    _assert_skipped(decision)


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


@pytest.mark.parametrize("element_class", ["IfcSlab", "IfcSlabStandardCase"])
def test_slab_uses_slab_vocabulary(element_class):
    """A mutação que aplique vocabulário de parede a uma laje deve quebrar este teste."""
    issue = _issue(property_name="", issue_type="system_unclassified", element_class=element_class)
    reading = MaterialReading(
        material_name="Piso porcelanato",
        layers=[{"name": "Porcelanato", "thickness_m": 0.01}],
        total_thickness_m=0.01,
    )

    decision = _derive(issue, element_type_name="Piso porcelanato", material_reading=reading)

    _assert_item(decision, "Piso cerâmico / porcelanato")


def test_predio_slab_standard_case_uses_legacy_slab_vocabulary():
    """A mutação que valide laje StandardCase como parede deve quebrar este teste."""
    issue = _issue(
        property_name="",
        issue_type="system_unclassified",
        element_class="IfcSlabStandardCase",
    )
    legacy = _legacy_item(
        issue,
        expected_value="Laje maciça de concreto armado",
        verified=True,
        notes="Sistema revisado pelo autor.",
    )

    decision = _audit_legacy(issue, legacy)

    _assert_item(decision, "Laje maciça de concreto armado")


def test_predio_rejects_legacy_system_vocabulary_for_unhandled_class():
    """A mutação que trate toda classe não-laje como parede deve quebrar este teste."""
    issue = _issue(
        property_name="",
        issue_type="system_unclassified",
        element_class="IfcBeam",
    )
    legacy = _legacy_item(
        issue,
        expected_value="Drywall / Steel frame",
        verified=True,
        notes="Revisado.",
    )

    decision = _audit_legacy(issue, legacy)

    _assert_skipped(decision)


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


def test_thermal_evidence_rejects_bool_before_float_coercion():
    """A mutação que converta True em 1.0 deve quebrar este teste."""
    with pytest.raises(ValidationError):
        ThermalEvidence(
            value=True,
            donor_guids=("DONOR-A",),
            unit="W/(m²·K)",
            conflicted=False,
        )


@pytest.mark.parametrize(
    ("target_guid", "donor_guid"),
    [
        ("TARGET-GUID", " TARGET-GUID "),
        (" TARGET-GUID ", "TARGET-GUID"),
    ],
)
def test_thermal_donor_guid_is_compared_after_stripping_both_sides(
    target_guid,
    donor_guid,
):
    """A mutação que normalize só o doador deve quebrar este teste."""
    issue = _issue(
        property_name="ThermalTransmittance",
        element_class="IfcWall",
        element_guid=target_guid,
    )
    evidence = ThermalEvidence(
        value=2.35,
        donor_guids=(donor_guid,),
        unit="W/(m²·K)",
        conflicted=False,
    )

    decision = _derive(issue, authored_thermal_by_type={("IfcWall", "TYPE-GUID"): evidence})

    _assert_skipped(decision)
    assert "doadora" in decision.skip_reason.lower()


def test_out_of_scope_property_is_skipped():
    """A mutação que rotule propriedade não auditada deve quebrar este teste."""
    issue = _issue(property_name="Reference", element_class="IfcWall")

    decision = _derive(issue)

    _assert_skipped(decision)
    assert decision.skip_reason == "fora do escopo evidence-audited-v1"
