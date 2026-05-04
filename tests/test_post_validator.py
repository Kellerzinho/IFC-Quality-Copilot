import ifcopenshell
import ifcopenshell.api
import ifcopenshell.guid

from src.models import OperationalRule
from src.validation.post_validator import PostValidator
from src.writer.ifc_writer import IFCWriter


def _make_wall(
    simple_ifc_file,
    pset_name: str = "Pset_WallCommon",
    props: dict | None = None,
):
    ifc_file, metadata = simple_ifc_file
    storey = metadata["storey"]
    wall = ifc_file.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name="Wall Test")
    ifc_file.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=storey,
        RelatedElements=[wall],
    )
    if props is not None:
        pset = ifcopenshell.api.run("pset.add_pset", ifc_file, product=wall, name=pset_name)
        ifcopenshell.api.run("pset.edit_pset", ifc_file, pset=pset, properties=props)
    return ifc_file, wall


def _thermal_rule() -> OperationalRule:
    return OperationalRule(
        source_spec="Thermal Spec",
        filter_entity="IfcWall",
        check_pset="Pset_WallCommon",
        check_property="ThermalTransmittance",
        check_type="is_numeric",
        severity="high",
    )


def test_valid_correction_passes(simple_ifc_file, monkeypatch):
    ifc_file, wall = _make_wall(
        simple_ifc_file,
        props={"IsExternal": True, "ThermalTransmittance": 2.48},
    )
    validator = PostValidator(ifc_file, [_thermal_rule()])
    monkeypatch.setattr(validator, "_run_schema_check", lambda: ([], []))

    result = validator.validate_element(wall.GlobalId)

    assert result.status == "pass"
    assert result.schema_valid is True
    assert result.ids_compliant is True
    assert result.errors == []


def test_ids_revalidation_passes_after_fix(simple_ifc_file, monkeypatch):
    ifc_file, wall = _make_wall(simple_ifc_file, props={"IsExternal": True})
    rule = _thermal_rule()
    validator = PostValidator(ifc_file, [rule])
    monkeypatch.setattr(validator, "_run_schema_check", lambda: ([], []))

    before = validator.validate_element(wall.GlobalId)
    IFCWriter(ifc_file).preencher_pset(
        wall.GlobalId,
        "Pset_WallCommon",
        {"ThermalTransmittance": 2.48},
    )
    after = validator.validate_element(wall.GlobalId)

    assert before.status == "fail"
    assert before.ids_compliant is False
    assert after.status == "pass"
    assert after.ids_compliant is True


def test_ids_revalidation_fails_if_still_missing(simple_ifc_file, monkeypatch):
    ifc_file, wall = _make_wall(simple_ifc_file, props={"IsExternal": True})
    validator = PostValidator(ifc_file, [_thermal_rule()])
    monkeypatch.setattr(validator, "_run_schema_check", lambda: ([], []))

    result = validator.validate_element(wall.GlobalId)

    assert result.status == "fail"
    assert result.schema_valid is True
    assert result.ids_compliant is False
    assert any("ThermalTransmittance" in error for error in result.errors)


def test_schema_check_graceful_when_unavailable(simple_ifc_file, monkeypatch):
    ifc_file, wall = _make_wall(
        simple_ifc_file,
        props={"IsExternal": True, "ThermalTransmittance": 2.48},
    )
    validator = PostValidator(ifc_file, [_thermal_rule()])

    real_import_module = __import__("importlib").import_module

    def fake_import_module(name: str):
        if name == "ifcopenshell.validate":
            raise ImportError("validate module unavailable")
        return real_import_module(name)

    monkeypatch.setattr("src.validation.post_validator.importlib.import_module", fake_import_module)

    result = validator.validate_element(wall.GlobalId)

    assert result.status == "pass"
    assert result.schema_valid is True
    assert result.ids_compliant is True
    assert any("Schema validation unavailable" in warning for warning in result.warnings)


def test_semantic_validation_rejects_non_canonical_fire_rating(simple_ifc_file, monkeypatch):
    ifc_file, wall = _make_wall(
        simple_ifc_file,
        props={"IsExternal": True, "ThermalTransmittance": 2.48, "FireRating": "60min"},
    )
    validator = PostValidator(ifc_file, [])
    monkeypatch.setattr(validator, "_run_schema_check", lambda: ([], []))

    result = validator.validate_element(wall.GlobalId)

    assert result.status == "fail"
    assert any("FireRating" in error for error in result.errors)


def test_semantic_validation_rejects_non_positive_thermal_transmittance(simple_ifc_file, monkeypatch):
    ifc_file, wall = _make_wall(
        simple_ifc_file,
        props={"IsExternal": True, "ThermalTransmittance": 0.0},
    )
    validator = PostValidator(ifc_file, [])
    monkeypatch.setattr(validator, "_run_schema_check", lambda: ([], []))

    result = validator.validate_element(wall.GlobalId)

    assert result.status == "fail"
    assert any("ThermalTransmittance" in error for error in result.errors)
