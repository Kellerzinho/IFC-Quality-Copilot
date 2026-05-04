"""Testes para src/translator/rule_generator.py."""

import pytest
import ifcopenshell
import ifcopenshell.api
import ifcopenshell.guid

from src.models import IDSSpecification, Issue, OperationalRule
from src.translator.rule_generator import apply_rules, generate_rules


# ---------------------------------------------------------------------------
# Fixtures locais
# ---------------------------------------------------------------------------


def _make_spec(
    name: str = "Spec Teste",
    entity: str = "IFCWALL",
    filters: list[dict] | None = None,
    requirements: list[dict] | None = None,
    description: str | None = None,
) -> IDSSpecification:
    """Cria IDSSpecification mínima para os testes."""
    return IDSSpecification(
        name=name,
        description=description,
        applicability_entity=entity,
        applicability_filters=filters or [],
        requirements=requirements or [],
    )


@pytest.fixture
def ifc_wall_file(simple_ifc_file) -> tuple[ifcopenshell.file, dict]:
    """Arquivo IFC2X3 com paredes para testar apply_rules.

    Paredes:
        - wall_ext_ok:  IsExternal=True, ThermalTransmittance=2.48  → deve passar
        - wall_ext_bad: IsExternal=True, ThermalTransmittance=None  → deve falhar
        - wall_int:     IsExternal=False, sem ThermalTransmittance   → deve ser ignorada
    """
    f, base_meta = simple_ifc_file
    storey = base_meta["storey"]

    def _wall(name: str, pset_props: dict | None) -> ifcopenshell.entity_instance:
        wall = f.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name=name)
        f.create_entity(
            "IfcRelContainedInSpatialStructure",
            GlobalId=ifcopenshell.guid.new(),
            RelatingStructure=storey,
            RelatedElements=[wall],
        )
        if pset_props is not None:
            pset = ifcopenshell.api.run("pset.add_pset", f, product=wall, name="Pset_WallCommon")
            ifcopenshell.api.run("pset.edit_pset", f, pset=pset, properties=pset_props)
        return wall

    wall_ext_ok = _wall("Wall Ext OK", {"IsExternal": True, "ThermalTransmittance": 2.48})
    wall_ext_bad = _wall("Wall Ext Bad", {"IsExternal": True, "ThermalTransmittance": None})
    wall_int = _wall("Wall Int", {"IsExternal": False})

    return f, {
        "wall_ext_ok": wall_ext_ok,
        "wall_ext_bad": wall_ext_bad,
        "wall_int": wall_int,
    }


# ---------------------------------------------------------------------------
# test_generate_rules_from_specs
# ---------------------------------------------------------------------------


def test_generate_rules_from_specs():
    """generate_rules deve retornar uma OperationalRule por requisito de cada spec."""
    specs = [
        _make_spec(
            entity="IFCWALL",
            filters=[{"pset": "Pset_WallCommon", "prop": "IsExternal", "value": "TRUE"}],
            requirements=[{"pset": "Pset_WallCommon", "prop": "ThermalTransmittance", "constraint": "exists"}],
        ),
        _make_spec(
            entity="IFCSPACE",
            requirements=[
                {"pset": "", "prop": "LongName", "constraint": "not_empty"},
                {"pset": "Pset_SpaceCommon", "prop": "Category", "constraint": "exists"},
            ],
        ),
    ]

    rules = generate_rules(specs)

    assert len(rules) == 3
    assert all(isinstance(r, OperationalRule) for r in rules)

    # Primeira regra: parede
    assert rules[0].filter_entity == "IfcWall"
    assert rules[0].check_pset == "Pset_WallCommon"
    assert rules[0].check_property == "ThermalTransmittance"

    # Segunda e terceira regras: espaço
    assert rules[1].filter_entity == "IfcSpace"
    assert rules[2].filter_entity == "IfcSpace"


def test_generate_rules_preserves_filter_conditions():
    """filter_conditions deve conter operator '==' para filtros com valor."""
    specs = [
        _make_spec(
            filters=[{"pset": "Pset_WallCommon", "prop": "IsExternal", "value": "TRUE"}],
            requirements=[{"pset": "Pset_WallCommon", "prop": "ThermalTransmittance", "constraint": "exists"}],
        ),
    ]

    rules = generate_rules(specs)

    assert len(rules[0].filter_conditions) == 1
    cond = rules[0].filter_conditions[0]
    assert cond["operator"] == "=="
    assert cond["value"] == "TRUE"


# ---------------------------------------------------------------------------
# test_generate_rules_correct_check_type
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("prop,constraint,expected_check_type", [
    ("ThermalTransmittance", "exists", "is_numeric"),
    ("ThermalTransmittance", "minInclusive", "is_numeric"),
    ("IsExternal", "exists", "is_boolean"),
    ("LoadBearing", "exists", "is_boolean"),
    ("equals:TRUE", "exists", "is_boolean"),  # constraint via equals:TRUE
    ("FireRating", "exists", "exists"),
    ("LongName", "not_empty", "not_empty"),
    ("Category", "pattern", "not_empty"),
])
def test_generate_rules_correct_check_type(prop: str, constraint: str, expected_check_type: str):
    """generate_rules deve inferir check_type correto para cada combinação prop/constraint."""
    # Para o caso especial "equals:TRUE" o prop é genérico
    actual_prop = prop if not prop.startswith("equals:") else "SomeFlag"
    actual_constraint = constraint if not prop.startswith("equals:") else prop

    specs = [
        _make_spec(
            requirements=[{"pset": "Pset_WallCommon", "prop": actual_prop, "constraint": actual_constraint}],
        ),
    ]

    rules = generate_rules(specs)

    assert len(rules) == 1
    assert rules[0].check_type == expected_check_type


def test_generate_rules_attribute_check_type():
    """Atributo direto (pset='') deve gerar check_type 'not_empty'."""
    specs = [
        _make_spec(
            entity="IFCSPACE",
            requirements=[{"pset": "", "prop": "LongName", "constraint": "not_empty"}],
        ),
    ]

    rules = generate_rules(specs)

    assert rules[0].check_type == "not_empty"
    assert rules[0].issue_type == "space_unnamed"


# ---------------------------------------------------------------------------
# test_apply_rules_detects_missing_thermal
# ---------------------------------------------------------------------------


def test_apply_rules_detects_missing_thermal(ifc_wall_file):
    """apply_rules deve criar Issue para parede externa sem ThermalTransmittance."""
    ifc_file, meta = ifc_wall_file

    rules = generate_rules([
        _make_spec(
            name="NBR 15575 Transmitância",
            entity="IFCWALL",
            filters=[{"pset": "Pset_WallCommon", "prop": "IsExternal", "value": "TRUE"}],
            requirements=[{"pset": "Pset_WallCommon", "prop": "ThermalTransmittance", "constraint": "exists"}],
        ),
    ])

    issues = apply_rules(ifc_file, rules)

    assert len(issues) == 1
    issue = issues[0]
    assert isinstance(issue, Issue)
    assert issue.element_guid == meta["wall_ext_bad"].GlobalId
    assert issue.issue_type == "pset_missing"
    assert issue.severity == "high"
    assert "ThermalTransmittance" in issue.description


# ---------------------------------------------------------------------------
# test_apply_rules_passes_filled_pset
# ---------------------------------------------------------------------------


def test_apply_rules_passes_filled_pset(ifc_wall_file):
    """apply_rules não deve criar Issue para parede com ThermalTransmittance preenchido."""
    ifc_file, meta = ifc_wall_file

    rules = generate_rules([
        _make_spec(
            entity="IFCWALL",
            filters=[{"pset": "Pset_WallCommon", "prop": "IsExternal", "value": "TRUE"}],
            requirements=[{"pset": "Pset_WallCommon", "prop": "ThermalTransmittance", "constraint": "exists"}],
        ),
    ])

    issues = apply_rules(ifc_file, rules)

    guids_with_issues = {i.element_guid for i in issues}
    assert meta["wall_ext_ok"].GlobalId not in guids_with_issues


# ---------------------------------------------------------------------------
# test_apply_rules_respects_filter_conditions
# ---------------------------------------------------------------------------


def test_apply_rules_respects_filter_conditions(ifc_wall_file):
    """apply_rules não deve verificar elementos que não satisfazem o filtro.

    wall_int tem IsExternal=False → não deve ser incluída no check de transmitância.
    """
    ifc_file, meta = ifc_wall_file

    rules = generate_rules([
        _make_spec(
            entity="IFCWALL",
            filters=[{"pset": "Pset_WallCommon", "prop": "IsExternal", "value": "TRUE"}],
            requirements=[{"pset": "Pset_WallCommon", "prop": "ThermalTransmittance", "constraint": "exists"}],
        ),
    ])

    issues = apply_rules(ifc_file, rules)

    guids_with_issues = {i.element_guid for i in issues}
    # wall_int não tem IsExternal=True → não entra no filtro → sem issue
    assert meta["wall_int"].GlobalId not in guids_with_issues


# ---------------------------------------------------------------------------
# test_apply_rules_deduplicates_issues
# ---------------------------------------------------------------------------


def test_apply_rules_deduplicates_issues(ifc_wall_file):
    """apply_rules não deve criar Issues duplicados para o mesmo elemento + propriedade."""
    ifc_file, _ = ifc_wall_file

    # Duas regras idênticas
    rule_a = OperationalRule(
        source_spec="Spec A",
        filter_entity="IfcWall",
        filter_conditions=[],
        check_pset="Pset_WallCommon",
        check_property="ThermalTransmittance",
        check_type="is_numeric",
        issue_type="pset_missing",
        severity="high",
    )
    rule_b = OperationalRule(
        source_spec="Spec B",
        filter_entity="IfcWall",
        filter_conditions=[],
        check_pset="Pset_WallCommon",
        check_property="ThermalTransmittance",
        check_type="is_numeric",
        issue_type="pset_missing",
        severity="high",
    )

    issues = apply_rules(ifc_file, [rule_a, rule_b])

    guids = [i.element_guid for i in issues]
    # Não deve haver guid duplicado para a mesma propriedade
    assert len(guids) == len(set(guids))
