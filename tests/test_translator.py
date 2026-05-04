"""Testes para src/translator/ids_parser.py e rule_generator.py."""

from pathlib import Path

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.api.owner.settings
import ifcopenshell.guid
import ifcopenshell.util.element

from src.models import IDSSpecification, OperationalRule, ReadinessProfile
from src.translator.ids_parser import parse_ids
from src.translator.rule_generator import apply_rules, generate_rules, generate_rules_for_profiles

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


# ---------------------------------------------------------------------------
# Helpers para testes de generate_rules
# ---------------------------------------------------------------------------

IDS_NS_DECL = (
    'xmlns:ids="http://standards.buildingsmart.org/IDS" '
    'xmlns:xs="http://www.w3.org/2001/XMLSchema"'
)


def _make_ids_xml(requirements_xml: str, entity: str = "IFCWALL") -> str:
    """Monta XML IDS mínimo com uma specification e os requirements fornecidos."""
    return f"""<?xml version="1.0" encoding="utf-8"?>
<ids:ids {IDS_NS_DECL}>
  <ids:specifications>
    <ids:specification name="Test">
      <ids:applicability>
        <ids:entity>
          <ids:name><ids:simpleValue>{entity}</ids:simpleValue></ids:name>
        </ids:entity>
      </ids:applicability>
      <ids:requirements>
        {requirements_xml}
      </ids:requirements>
    </ids:specification>
  </ids:specifications>
</ids:ids>"""


def _make_spec(
    entity: str,
    pset: str,
    prop: str,
    constraint: str = "exists",
    facet_type: str = "property",
) -> IDSSpecification:
    """Cria IDSSpecification mínima com um único requisito."""
    return IDSSpecification(
        name="Spec Teste",
        applicability_entity=entity,
        requirements=[{
            "facet_type": facet_type,
            "pset": pset,
            "prop": prop,
            "constraint": constraint,
            "constraint_type": "",
        }],
    )


def _make_profile(**kwargs) -> ReadinessProfile:
    """Cria ReadinessProfile mínimo para testes."""
    defaults = dict(
        id="energy_readiness",
        name="Energy-readiness",
        description="Perfil de teste.",
    )
    defaults.update(kwargs)
    return ReadinessProfile(**defaults)


# ---------------------------------------------------------------------------
# Testes de inferência em generate_rules
# ---------------------------------------------------------------------------

def test_generate_rules_thermal_gets_lookup_strategy():
    """Requisito de ThermalTransmittance deve gerar regra com suggestion_strategy='lookup_table'."""
    spec = _make_spec("IFCWALL", "Pset_WallCommon", "ThermalTransmittance")
    rules = generate_rules([spec])

    assert len(rules) == 1
    assert rules[0].suggestion_strategy == "lookup_table"


def test_generate_rules_quantities_gets_geometric_strategy():
    """Requisito em Qto_ deve gerar regra com suggestion_strategy='geometric_calc'."""
    spec = _make_spec("IFCWALL", "Qto_WallBaseQuantities", "NetSideArea", facet_type="quantity")
    rules = generate_rules([spec])

    assert len(rules) == 1
    assert rules[0].suggestion_strategy == "geometric_calc"


def test_generate_rules_space_gets_llm_strategy():
    """Requisito de LongName em IfcSpace deve gerar regra com suggestion_strategy='llm_inference'."""
    spec = _make_spec("IFCSPACE", "", "LongName", "not_empty")
    rules = generate_rules([spec])

    assert len(rules) == 1
    assert rules[0].suggestion_strategy == "llm_inference"


def test_generate_rules_with_profile_populates_profile_id():
    """Com profile, regras devem ter profile_id e tags preenchidos a partir do perfil."""
    profile = _make_profile(id="energy_readiness")
    spec = _make_spec("IFCWALL", "Pset_WallCommon", "ThermalTransmittance")
    rules = generate_rules([spec], profile=profile)

    assert len(rules) == 1
    assert rules[0].profile_id == "energy_readiness"
    assert "energy_readiness" in rules[0].tags


def test_generate_rules_classification_gets_domain_metadata():
    spec = _make_spec("IFCWALL", "Uniclass", "Ss_20_10_30", "equals:Ss_20_10_30", facet_type="classification")
    profile = _make_profile(
        id="budget_readiness",
        supported_data_categories=["classification", "quantity"],
        external_classification_systems=["Uniclass"],
    )

    rules = generate_rules([spec], profile=profile)

    assert rules[0].issue_type == "classification_missing"
    assert rules[0].suggestion_strategy == "copy_from_source"
    assert rules[0].write_action == "mapear_classificacao"
    assert rules[0].required_context == ["classifications"]
    assert "facet:classification" in rules[0].tags
    assert "classification:Uniclass" in rules[0].tags


def test_generate_rules_for_profiles_merges_multiple_ids_sources():
    energy_profile = _make_profile(id="energy_readiness")
    fm_profile = _make_profile(id="fm_readiness")
    energy_spec = _make_spec("IFCWALL", "Pset_WallCommon", "ThermalTransmittance")
    fm_spec = _make_spec("IFCSPACE", "", "LongName", "not_empty")

    rules = generate_rules_for_profiles([
        ([energy_spec], energy_profile),
        ([fm_spec], fm_profile),
    ])

    assert len(rules) == 2
    assert {rule.profile_id for rule in rules} == {"energy_readiness", "fm_readiness"}


def test_generate_rules_infers_write_action():
    """Requisito de LongName em IfcSpace deve gerar regra com write_action='renomear_espaco'."""
    spec = _make_spec("IFCSPACE", "", "LongName", "not_empty")
    rules = generate_rules([spec])

    assert len(rules) == 1
    assert rules[0].write_action == "renomear_espaco"


def test_generate_rules_infers_required_context():
    """Requisito de ThermalTransmittance deve gerar required_context com campos de envoltória."""
    spec = _make_spec("IFCWALL", "Pset_WallCommon", "ThermalTransmittance")
    rules = generate_rules([spec])

    assert rules[0].required_context == ["material", "thickness", "is_external", "layers"]


def test_generate_rules_quantities_infers_geometry_context():
    """Requisito em Qto_ deve gerar required_context com ['geometry', 'bounding_box']."""
    spec = _make_spec("IFCWALL", "Qto_WallBaseQuantities", "NetSideArea", facet_type="quantity")
    rules = generate_rules([spec])

    assert rules[0].required_context == ["geometry", "bounding_box"]


def test_generate_rules_without_profile_leaves_profile_id_none():
    """Sem profile, profile_id e tags devem permanecer com defaults."""
    spec = _make_spec("IFCWALL", "Pset_WallCommon", "ThermalTransmittance")
    rules = generate_rules([spec])

    assert rules[0].profile_id is None
    assert rules[0].tags == []


def test_generate_rules_quantities_infers_write_action():
    """Requisito em Qto_ deve gerar write_action='preencher_base_quantities'."""
    spec = _make_spec("IFCWALL", "Qto_WallBaseQuantities", "NetSideArea", facet_type="quantity")
    rules = generate_rules([spec])

    assert rules[0].write_action == "preencher_base_quantities"


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


# ---------------------------------------------------------------------------
# Testes de facets adicionais (parse_ids com XML inline)
# ---------------------------------------------------------------------------

def test_parse_ids_with_restriction(tmp_path: Path) -> None:
    """<xs:restriction base="xs:double"><xs:minInclusive> deve resultar em
    constraint='minInclusive' e constraint_type='xs:double'."""
    xml = _make_ids_xml("""
        <ids:property>
          <ids:propertySet><ids:simpleValue>Pset_WallCommon</ids:simpleValue></ids:propertySet>
          <ids:baseName><ids:simpleValue>ThermalTransmittance</ids:simpleValue></ids:baseName>
          <ids:value>
            <xs:restriction base="xs:double">
              <xs:minInclusive value="0"/>
            </xs:restriction>
          </ids:value>
        </ids:property>
    """)
    ids_file = tmp_path / "test.ids"
    ids_file.write_text(xml, encoding="utf-8")

    specs = parse_ids(str(ids_file))
    req = specs[0].requirements[0]

    assert req["constraint"] == "minInclusive"
    assert req["constraint_type"] == "xs:double"


def test_parse_energy_ids_reads_thermal_specs(tmp_path: Path) -> None:
    """Requisito de ThermalTransmittance com restriction double deve ter
    facet_type='property' e constraint_type='xs:double'."""
    xml = _make_ids_xml("""
        <ids:property>
          <ids:propertySet><ids:simpleValue>Pset_WallCommon</ids:simpleValue></ids:propertySet>
          <ids:baseName><ids:simpleValue>ThermalTransmittance</ids:simpleValue></ids:baseName>
          <ids:value>
            <xs:restriction base="xs:double">
              <xs:minInclusive value="0"/>
            </xs:restriction>
          </ids:value>
        </ids:property>
    """)
    ids_file = tmp_path / "test.ids"
    ids_file.write_text(xml, encoding="utf-8")

    specs = parse_ids(str(ids_file))
    req = specs[0].requirements[0]

    assert req["facet_type"] == "property"
    assert req["prop"] == "ThermalTransmittance"
    assert req["pset"] == "Pset_WallCommon"
    assert req["constraint_type"] == "xs:double"


def test_parse_budget_ids_reads_quantity_facets(tmp_path: Path) -> None:
    """<property> com pset Qto_ deve resultar em facet_type='quantity'."""
    xml = _make_ids_xml("""
        <ids:property>
          <ids:propertySet><ids:simpleValue>Qto_WallBaseQuantities</ids:simpleValue></ids:propertySet>
          <ids:baseName><ids:simpleValue>NetSideArea</ids:simpleValue></ids:baseName>
        </ids:property>
    """)
    ids_file = tmp_path / "test.ids"
    ids_file.write_text(xml, encoding="utf-8")

    specs = parse_ids(str(ids_file))
    req = specs[0].requirements[0]

    assert req["facet_type"] == "quantity"
    assert req["pset"] == "Qto_WallBaseQuantities"
    assert req["prop"] == "NetSideArea"
    assert req["constraint"] == "exists"
    assert req["constraint_type"] == ""


def test_parse_ids_material_facet(tmp_path: Path) -> None:
    """<material> com simpleValue deve resultar em facet_type='material' e prop correto."""
    xml = _make_ids_xml("""
        <ids:material>
          <ids:value><ids:simpleValue>Concrete</ids:simpleValue></ids:value>
        </ids:material>
    """)
    ids_file = tmp_path / "test.ids"
    ids_file.write_text(xml, encoding="utf-8")

    specs = parse_ids(str(ids_file))

    assert len(specs[0].requirements) == 1
    req = specs[0].requirements[0]
    assert req["facet_type"] == "material"
    assert req["pset"] == ""
    assert req["prop"] == "Concrete"
    assert req["constraint"] == "equals:Concrete"
    assert req["constraint_type"] == "xs:string"


def test_parse_ids_classification_facet(tmp_path: Path) -> None:
    """<classification> deve resultar em facet_type='classification',
    pset=sistema e prop=código."""
    xml = _make_ids_xml("""
        <ids:classification>
          <ids:system><ids:simpleValue>Uniclass</ids:simpleValue></ids:system>
          <ids:value><ids:simpleValue>Ss_20_10_30</ids:simpleValue></ids:value>
        </ids:classification>
    """)
    ids_file = tmp_path / "test.ids"
    ids_file.write_text(xml, encoding="utf-8")

    specs = parse_ids(str(ids_file))
    req = specs[0].requirements[0]

    assert req["facet_type"] == "classification"
    assert req["pset"] == "Uniclass"
    assert req["prop"] == "Ss_20_10_30"
    assert req["constraint"] == "equals:Ss_20_10_30"
    assert req["constraint_type"] == "xs:string"


def test_parse_ids_partof_facet(tmp_path: Path) -> None:
    """<partOf> deve resultar em facet_type='relation', pset='IFC_RELATION'
    e prop com o nome da entidade contenedora."""
    xml = _make_ids_xml("""
        <ids:partOf>
          <ids:entity>
            <ids:name><ids:simpleValue>IFCBUILDINGSTOREY</ids:simpleValue></ids:name>
          </ids:entity>
        </ids:partOf>
    """)
    ids_file = tmp_path / "test.ids"
    ids_file.write_text(xml, encoding="utf-8")

    specs = parse_ids(str(ids_file))
    req = specs[0].requirements[0]

    assert req["facet_type"] == "relation"
    assert req["pset"] == "IFC_RELATION"
    assert req["prop"] == "IFCBUILDINGSTOREY"
    assert req["constraint"] == "exists"
    assert req["constraint_type"] == ""
