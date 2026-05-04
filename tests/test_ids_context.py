import ifcopenshell
import ifcopenshell.api
import ifcopenshell.api.owner.settings
import ifcopenshell.guid

from src.models import IDSContext, OperationalRule
from src.translator.rule_generator import apply_rules


def _make_ifc() -> ifcopenshell.file:
    f = ifcopenshell.api.run("project.create_file", version="IFC2X3")
    person = ifcopenshell.api.run("owner.add_person", f, identification="eng", family_name="Engineer")
    org = ifcopenshell.api.run("owner.add_organisation", f, identification="IFC", name="IFC Test")
    user = ifcopenshell.api.run("owner.add_person_and_organisation", f, person=person, organisation=org)
    app = ifcopenshell.api.run("owner.add_application", f)
    ifcopenshell.api.owner.settings.get_user = lambda ifc: user
    ifcopenshell.api.owner.settings.get_application = lambda ifc: app
    return f


def _wall_with_pset(
    f: ifcopenshell.file,
    props: dict,
    pset_name: str = "Pset_WallCommon",
) -> ifcopenshell.entity_instance:
    wall = f.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name="Wall Test")
    pset = ifcopenshell.api.run("pset.add_pset", f, product=wall, name=pset_name)
    ifcopenshell.api.run("pset.edit_pset", f, pset=pset, properties=props)
    return wall


def test_issue_from_ids_has_ids_context() -> None:
    f = _make_ifc()
    wall = _wall_with_pset(f, {"IsExternal": True})
    rule = OperationalRule(
        source_spec="NBR 15575 Thermal",
        filter_entity="IfcWall",
        filter_conditions=[{"pset": "Pset_WallCommon", "prop": "IsExternal", "operator": "==", "value": "TRUE"}],
        check_pset="Pset_WallCommon",
        check_property="ThermalTransmittance",
        check_type="is_numeric",
        issue_type="pset_missing",
        severity="high",
        evidence_source="W/(m²·K)",
    )

    issues = apply_rules(f, [rule])

    assert len(issues) == 1
    assert issues[0].element_guid == wall.GlobalId
    ids_context = issues[0].context["ids_context"]
    assert ids_context["spec_name"] == "NBR 15575 Thermal"
    assert ids_context["check_type"] == "is_numeric"
    assert ids_context["expected_pset"] == "Pset_WallCommon"
    assert ids_context["expected_property"] == "ThermalTransmittance"
    assert ids_context["expected_value"] is None
    assert ids_context["expected_unit"] == "W/(m²·K)"
    assert ids_context["severity"] == "high"
    assert ids_context["requirement_description"] == (
        "Pset_WallCommon.ThermalTransmittance must exist and be numeric"
    )


def test_ids_context_serialization() -> None:
    context = IDSContext(
        spec_name="Spec Thermal",
        requirement_description="Pset_WallCommon.ThermalTransmittance must exist and be numeric",
        check_type="is_numeric",
        expected_pset="Pset_WallCommon",
        expected_property="ThermalTransmittance",
        expected_value=None,
        expected_unit="W/(m²·K)",
        severity="high",
    )

    payload = context.model_dump()
    restored = IDSContext(**payload)

    assert restored.spec_name == "Spec Thermal"
    assert restored.requirement_description == context.requirement_description
    assert restored.expected_pset == "Pset_WallCommon"
    assert restored.expected_property == "ThermalTransmittance"
    assert restored.expected_unit == "W/(m²·K)"
    assert restored.severity == "high"
