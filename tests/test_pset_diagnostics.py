"""Testes para o módulo de diagnóstico de Psets."""

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.guid
import pytest

from src.ifc_analyzer.pset_diagnostics import (
    DEFAULT_REQUIRED_PSETS,
    _extract_element_material_context,
    _is_empty_value,
    diagnose_psets,
)


# ---------------------------------------------------------------------------
# _is_empty_value
# ---------------------------------------------------------------------------


def test_is_empty_value_none():
    assert _is_empty_value(None, "ThermalTransmittance") is True


def test_is_empty_value_empty_string():
    assert _is_empty_value("", "FireRating") is True


def test_is_empty_value_whitespace_string():
    assert _is_empty_value("   ", "FireRating") is True


def test_is_empty_value_zero_thermal():
    """ThermalTransmittance=0.0 é fisicamente impossível e deve ser flagrado."""
    assert _is_empty_value(0.0, "ThermalTransmittance") is True


def test_is_empty_value_valid_float():
    assert _is_empty_value(2.48, "ThermalTransmittance") is False


def test_is_empty_value_false_boolean_is_valid():
    """False é valor legítimo para IsExternal e similares."""
    assert _is_empty_value(False, "IsExternal") is False


def test_is_empty_value_zero_not_flagged_for_non_thermal():
    """0.0 só é inválido para propriedades em _ZERO_IS_INVALID."""
    assert _is_empty_value(0.0, "IsLoadBearing") is False


# ---------------------------------------------------------------------------
# diagnose_psets — detecção de problemas
# ---------------------------------------------------------------------------


def test_diagnose_psets_detects_missing_thermal(ifc_with_walls):
    """Wall 1 (ThermalTransmittance=None) deve gerar issue para essa propriedade."""
    ifc_file, metadata = ifc_with_walls

    issues = diagnose_psets(ifc_file)

    tt_issues = [
        i for i in issues
        if i.element_guid == metadata["wall1_guid"]
        and i.context["check_property"] == "ThermalTransmittance"
    ]
    assert len(tt_issues) == 1
    assert tt_issues[0].issue_type == "pset_missing"


def test_diagnose_psets_severity_thermal_is_high(ifc_with_walls):
    """Issue de ThermalTransmittance deve ter severidade 'high'."""
    ifc_file, metadata = ifc_with_walls

    issues = diagnose_psets(ifc_file)

    tt_issue = next(
        (i for i in issues
         if i.element_guid == metadata["wall1_guid"]
         and i.context["check_property"] == "ThermalTransmittance"),
        None,
    )
    assert tt_issue is not None
    assert tt_issue.severity == "high"


def test_diagnose_psets_ignores_filled_pset(ifc_with_walls):
    """Wall 2 (ThermalTransmittance=2.48) não deve gerar issue para essa propriedade."""
    ifc_file, metadata = ifc_with_walls

    issues = diagnose_psets(ifc_file)

    tt_issues_wall2 = [
        i for i in issues
        if i.element_guid == metadata["wall2_guid"]
        and i.context["check_property"] == "ThermalTransmittance"
    ]
    assert len(tt_issues_wall2) == 0


def test_diagnose_psets_detects_empty_value(simple_ifc_file):
    """Propriedade presente no Pset com valor '' (string vazia) deve gerar issue."""
    ifc_file, base_meta = simple_ifc_file
    storey = base_meta["storey"]

    wall = ifc_file.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name="Wall FR")
    ifc_file.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=storey,
        RelatedElements=[wall],
    )
    pset = ifcopenshell.api.run("pset.add_pset", ifc_file, product=wall, name="Pset_WallCommon")
    ifcopenshell.api.run(
        "pset.edit_pset", ifc_file, pset=pset,
        properties={"IsExternal": True, "ThermalTransmittance": 2.5, "FireRating": ""},
    )

    issues = diagnose_psets(ifc_file)

    fr_issues = [
        i for i in issues
        if i.element_guid == wall.GlobalId
        and i.context["check_property"] == "FireRating"
    ]
    assert len(fr_issues) == 1
    assert fr_issues[0].severity == "high"


def test_diagnose_psets_wall_without_any_pset(ifc_with_walls):
    """Wall 3 (sem Pset_WallCommon) deve gerar issue para cada propriedade requerida."""
    ifc_file, metadata = ifc_with_walls
    required_props = DEFAULT_REQUIRED_PSETS["IfcWall"]["Pset_WallCommon"]

    issues = diagnose_psets(ifc_file)

    wall3_issues = [i for i in issues if i.element_guid == metadata["wall3_guid"]]
    missing_props = {i.context["check_property"] for i in wall3_issues}

    for prop in required_props:
        assert prop in missing_props, f"Propriedade '{prop}' deveria estar faltando em Wall 3"


def test_diagnose_psets_custom_required_psets(ifc_with_walls):
    """Ao passar required_psets customizado, apenas as regras informadas são aplicadas."""
    ifc_file, metadata = ifc_with_walls

    custom = {"IfcWall": {"Pset_WallCommon": ["IsExternal"]}}
    issues = diagnose_psets(ifc_file, required_psets=custom)

    # Apenas IsExternal deve ser verificada — não deve haver issues de ThermalTransmittance
    prop_names = {i.context["check_property"] for i in issues}
    assert "ThermalTransmittance" not in prop_names
    assert "FireRating" not in prop_names


def test_diagnose_psets_custom_respects_only_missing(ifc_with_walls):
    """Com custom psets, Wall 2 (IsExternal=True) não gera issue para IsExternal."""
    ifc_file, metadata = ifc_with_walls

    custom = {"IfcWall": {"Pset_WallCommon": ["IsExternal"]}}
    issues = diagnose_psets(ifc_file, required_psets=custom)

    wall2_issues = [i for i in issues if i.element_guid == metadata["wall2_guid"]]
    assert len(wall2_issues) == 0


def test_diagnose_psets_returns_empty_for_clean_model(simple_ifc_file):
    """Modelo sem nenhuma classe requerida deve retornar lista vazia."""
    ifc_file, _ = simple_ifc_file

    issues = diagnose_psets(ifc_file)

    assert issues == []


def test_diagnose_psets_issue_description_format(ifc_with_walls):
    """Description do issue deve seguir o formato '{Class} #{guid}: {pset}.{prop} ausente'."""
    ifc_file, metadata = ifc_with_walls

    issues = diagnose_psets(ifc_file)

    tt_issue = next(
        i for i in issues
        if i.element_guid == metadata["wall1_guid"]
        and i.context["check_property"] == "ThermalTransmittance"
    )
    expected = f"IfcWall #{metadata['wall1_guid'][:8]}: Pset_WallCommon.ThermalTransmittance ausente"
    assert tt_issue.description == expected


def test_diagnose_psets_medium_severity_for_other_props(ifc_with_walls):
    """Propriedades não-críticas (IsExternal, IsLoadBearing) devem ter severidade 'medium'."""
    ifc_file, metadata = ifc_with_walls

    issues = diagnose_psets(ifc_file)

    medium_props = {"IsExternal", "IsLoadBearing", "LoadBearing", "Category"}
    for issue in issues:
        if issue.context["check_property"] in medium_props:
            assert issue.severity == "medium", (
                f"{issue.context['check_property']} deveria ser 'medium', "
                f"mas é '{issue.severity}'"
            )


# ---------------------------------------------------------------------------
# diagnose_psets — contexto do issue
# ---------------------------------------------------------------------------


def test_diagnose_psets_context_has_material(ifc_with_walls):
    """Issue de Wall 1 deve ter element_material no contexto."""
    ifc_file, metadata = ifc_with_walls

    issues = diagnose_psets(ifc_file)

    tt_issue = next(
        i for i in issues
        if i.element_guid == metadata["wall1_guid"]
        and i.context["check_property"] == "ThermalTransmittance"
    )
    # Wall 1 tem material "Bloco cerâmico 14cm"
    assert tt_issue.context["material_name"] is not None


def test_diagnose_psets_context_has_thickness(ifc_with_walls):
    """Issue de Wall 1 deve ter element_thickness ~ 0.14 no contexto."""
    ifc_file, metadata = ifc_with_walls

    issues = diagnose_psets(ifc_file)

    tt_issue = next(
        i for i in issues
        if i.element_guid == metadata["wall1_guid"]
        and i.context["check_property"] == "ThermalTransmittance"
    )
    assert tt_issue.context["thickness_m"] == pytest.approx(0.14)


def test_diagnose_psets_context_is_external(ifc_with_walls):
    """Issue de Wall 1 deve reportar is_external=True no contexto."""
    ifc_file, metadata = ifc_with_walls

    issues = diagnose_psets(ifc_file)

    tt_issue = next(
        i for i in issues
        if i.element_guid == metadata["wall1_guid"]
        and i.context["check_property"] == "ThermalTransmittance"
    )
    assert tt_issue.context["is_external"] is True


def test_diagnose_psets_context_existing_psets_no_id(ifc_with_walls):
    """existing_psets no contexto não deve conter a chave interna 'id'."""
    ifc_file, metadata = ifc_with_walls

    issues = diagnose_psets(ifc_file)

    for issue in issues:
        for props in issue.context["existing_psets"].values():
            assert "id" not in props


# ---------------------------------------------------------------------------
# _extract_element_material_context
# ---------------------------------------------------------------------------


def test_extract_material_context_layer_set(ifc_with_walls):
    """Parede com IfcMaterialLayerSetUsage deve retornar thickness_m e layers."""
    ifc_file, metadata = ifc_with_walls

    ctx = _extract_element_material_context(metadata["wall1"], ifc_file)

    assert ctx["thickness_m"] == pytest.approx(0.14)
    assert len(ctx["layers"]) == 1
    assert ctx["layers"][0]["thickness_m"] == pytest.approx(0.14)


def test_extract_material_context_no_material(simple_ifc_file):
    """Elemento sem material deve retornar campos None/[] sem lançar exceção."""
    ifc_file, base_meta = simple_ifc_file

    wall = ifc_file.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name="No Mat")
    ctx = _extract_element_material_context(wall, ifc_file)

    assert ctx["material_name"] is None
    assert ctx["thickness_m"] is None
    assert ctx["layers"] == []
