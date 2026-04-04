"""Testes para src/translator/ids_parser.py e rule_generator.py."""

from pathlib import Path

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.api.owner.settings
import ifcopenshell.guid
import ifcopenshell.util.element

from src.models import IDSSpecification, OperationalRule
from src.translator.ids_parser import parse_ids
from src.translator.rule_generator import apply_rules

IDS_PATH = str(Path(__file__).parent.parent / "data" / "ids_templates" / "residencial_nbr15575.ids")


def test_parse_ids_reads_file():
    """parse_ids deve retornar uma lista (não levantar exceção)."""
    result = parse_ids(IDS_PATH)
    assert isinstance(result, list)


def test_parse_ids_extracts_5_specs():
    """parse_ids deve retornar exatamente 5 IDSSpecification do arquivo NBR 15575."""
    result = parse_ids(IDS_PATH)
    assert len(result) == 5
    assert all(isinstance(s, IDSSpecification) for s in result)


def test_parse_ids_wall_thermal_spec():
    """Primeira spec deve cobrir paredes externas com ThermalTransmittance."""
    specs = parse_ids(IDS_PATH)
    spec = specs[0]

    assert spec.applicability_entity == "IFCWALL"
    # filtro de aplicabilidade: IsExternal = TRUE
    assert len(spec.applicability_filters) == 1
    filt = spec.applicability_filters[0]
    assert filt["pset"] == "Pset_WallCommon"
    assert filt["prop"] == "IsExternal"
    assert filt["value"] == "TRUE"
    # requisito: ThermalTransmittance
    assert len(spec.requirements) == 1
    req = spec.requirements[0]
    assert req["pset"] == "Pset_WallCommon"
    assert req["prop"] == "ThermalTransmittance"


def test_parse_ids_space_name_spec():
    """Terceira spec deve cobrir IfcSpace com requisito de LongName não vazio."""
    specs = parse_ids(IDS_PATH)
    spec = specs[2]

    assert spec.applicability_entity == "IFCSPACE"
    assert spec.applicability_filters == []
    assert len(spec.requirements) == 1
    req = spec.requirements[0]
    assert req["prop"] == "LongName"
    assert req["pset"] == ""
    assert req["constraint"] == "not_empty"


# ---------------------------------------------------------------------------
# Helpers para testes de apply_rules
# ---------------------------------------------------------------------------

def _make_ifc() -> ifcopenshell.file:
    """Cria arquivo IFC2X3 mínimo com owner configurado para testes de apply_rules."""
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
    """Cria IfcWall com as propriedades informadas no pset_name."""
    wall = f.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name="Wall Test")
    pset = ifcopenshell.api.run("pset.add_pset", f, product=wall, name=pset_name)
    ifcopenshell.api.run("pset.edit_pset", f, pset=pset, properties=props)
    return wall


def _rule_thermal(filter_is_external: bool = True) -> OperationalRule:
    """OperationalRule que exige ThermalTransmittance numérico em paredes externas."""
    conditions = (
        [{"pset": "Pset_WallCommon", "prop": "IsExternal", "operator": "==", "value": "TRUE"}]
        if filter_is_external
        else []
    )
    return OperationalRule(
        source_spec="NBR 15575 Thermal",
        filter_entity="IfcWall",
        filter_conditions=conditions,
        check_pset="Pset_WallCommon",
        check_property="ThermalTransmittance",
        check_type="is_numeric",
        severity="high",
    )


# ---------------------------------------------------------------------------
# Testes de apply_rules
# ---------------------------------------------------------------------------

def test_apply_rules_wall_missing_thermal():
    """Parede externa sem ThermalTransmittance gera 1 Issue high."""
    f = _make_ifc()
    wall = _wall_with_pset(f, {"IsExternal": True})
    # ThermalTransmittance NÃO está no pset

    issues = apply_rules(f, [_rule_thermal()])

    assert len(issues) == 1
    issue = issues[0]
    assert issue.element_guid == wall.GlobalId
    assert issue.severity == "high"
    assert issue.issue_type == "pset_missing"
    assert "ThermalTransmittance" in issue.description
    assert "NBR 15575 Thermal" in issue.description


def test_apply_rules_wall_with_thermal_passes():
    """Parede externa com ThermalTransmittance numérico positivo não gera Issue."""
    f = _make_ifc()
    _wall_with_pset(f, {"IsExternal": True, "ThermalTransmittance": 2.48})

    issues = apply_rules(f, [_rule_thermal()])

    assert issues == []


def test_apply_rules_filter_is_external_true():
    """Parede sem IsExternal=True não passa no filtro e não gera Issue."""
    f = _make_ifc()
    _wall_with_pset(f, {"IsExternal": False})
    # Filtro exige IsExternal == TRUE → elemento rejeitado

    issues = apply_rules(f, [_rule_thermal(filter_is_external=True)])

    assert issues == []


def test_apply_rules_space_empty_longname():
    """IfcSpace com LongName vazio gera Issue para regra not_empty."""
    f = _make_ifc()
    space = f.create_entity(
        "IfcSpace",
        GlobalId=ifcopenshell.guid.new(),
        Name="Room 1",
        LongName="",
    )

    rule = OperationalRule(
        source_spec="NBR 15575 Space",
        filter_entity="IfcSpace",
        filter_conditions=[],
        check_pset="",
        check_property="LongName",
        check_type="not_empty",
        issue_type="space_unnamed",
        severity="low",
    )

    issues = apply_rules(f, [rule])

    assert len(issues) == 1
    assert issues[0].element_guid == space.GlobalId
    assert issues[0].issue_type == "space_unnamed"
    assert "LongName" in issues[0].description


def test_apply_rules_unknown_entity_skipped():
    """Regra com filter_entity inexistente não levanta exceção e retorna lista vazia."""
    f = _make_ifc()

    rule = OperationalRule(
        source_spec="Spec Fantasma",
        filter_entity="IfcClasseQueNaoExiste",
        filter_conditions=[],
        check_pset="Pset_X",
        check_property="PropX",
        check_type="exists",
        severity="low",
    )

    issues = apply_rules(f, [rule])

    assert issues == []


def test_apply_rules_boolean_filter():
    """Filtro com operador '!=' exclui parede com IsExternal=True do check."""
    f = _make_ifc()
    # Parede externa: IsExternal=True → filtro != TRUE rejeita → sem Issue
    _wall_with_pset(f, {"IsExternal": True, "ThermalTransmittance": None})
    # Parede interna: IsExternal=False → filtro != TRUE aceita → Issue (Thermal ausente)
    wall_int = _wall_with_pset(f, {"IsExternal": False})

    rule = OperationalRule(
        source_spec="Internal Walls",
        filter_entity="IfcWall",
        filter_conditions=[
            {"pset": "Pset_WallCommon", "prop": "IsExternal", "operator": "!=", "value": "TRUE"}
        ],
        check_pset="Pset_WallCommon",
        check_property="ThermalTransmittance",
        check_type="is_numeric",
        severity="medium",
    )

    issues = apply_rules(f, [rule])

    assert len(issues) == 1
    assert issues[0].element_guid == wall_int.GlobalId
