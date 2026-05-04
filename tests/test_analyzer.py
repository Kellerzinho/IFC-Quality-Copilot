"""Testes para os módulos de diagnóstico IFC."""

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.guid
import pytest

from src.ifc_analyzer.space_diagnostics import (
    diagnose_spaces,
    _extract_space_context,
    _classify_sanitary_terminal,
    _get_functional_label,
)


# ---------------------------------------------------------------------------
# diagnose_spaces
# ---------------------------------------------------------------------------


def test_diagnose_spaces_detects_generic_room(ifc_with_spaces):
    """Espaços com nomes genéricos ('Room 1', 'Room 2', 'Room') geram Issues."""
    ifc_file, metadata = ifc_with_spaces

    issues = diagnose_spaces(ifc_file)

    # Cozinha não deve ser detectado; Room 1, Room 2 e Room (LongName="") devem
    assert len(issues) == 3
    guids = {i.element_guid for i in issues}
    assert metadata["space1_guid"] in guids  # Room 1
    assert metadata["space2_guid"] in guids  # Room 2
    assert metadata["space4_guid"] in guids  # Room / LongName=""


def test_diagnose_spaces_ignores_named_space(ifc_with_spaces):
    """Espaço com nome funcional ('Cozinha') não deve gerar Issue."""
    ifc_file, metadata = ifc_with_spaces

    issues = diagnose_spaces(ifc_file)

    guids = {i.element_guid for i in issues}
    assert metadata["space3_guid"] not in guids


def test_diagnose_spaces_detects_empty_longname(ifc_with_spaces):
    """LongName vazio deve ser tratado como nome genérico."""
    ifc_file, metadata = ifc_with_spaces

    issues = diagnose_spaces(ifc_file)

    guids = {i.element_guid for i in issues}
    assert metadata["space4_guid"] in guids


def test_diagnose_spaces_issue_fields(ifc_with_spaces):
    """Issue gerado tem issue_type, severity e description corretos."""
    ifc_file, _ = ifc_with_spaces

    issues = diagnose_spaces(ifc_file)

    for issue in issues:
        assert issue.issue_type == "space_unnamed"
        assert issue.severity == "low"
        assert issue.element_class == "IfcSpace"
        assert "não possui nome funcional" in issue.description


def test_diagnose_spaces_context_has_area(ifc_with_spaces):
    """Issue de espaço com Qto_SpaceBaseQuantities deve ter area_m2 no contexto."""
    ifc_file, metadata = ifc_with_spaces

    issues = diagnose_spaces(ifc_file)

    # space1 (Room 1) tem NetFloorArea=4.2
    issue_space1 = next(i for i in issues if i.element_guid == metadata["space1_guid"])
    assert issue_space1.context.get("area_m2") == pytest.approx(4.2)


def test_diagnose_spaces_context_has_floor(ifc_with_spaces):
    """Issue de espaço deve ter o nome do pavimento pai no contexto."""
    ifc_file, metadata = ifc_with_spaces

    issues = diagnose_spaces(ifc_file)

    issue_space1 = next(i for i in issues if i.element_guid == metadata["space1_guid"])
    assert issue_space1.context.get("floor") == "Pavimento 1"


def test_diagnose_spaces_returns_empty_for_clean_model(simple_ifc_file):
    """Modelo sem IfcSpace deve retornar lista vazia."""
    ifc_file, _ = simple_ifc_file

    issues = diagnose_spaces(ifc_file)

    assert issues == []


# ---------------------------------------------------------------------------
# _extract_space_context
# ---------------------------------------------------------------------------


def test_extract_space_context_area(ifc_with_spaces):
    """_extract_space_context retorna area_m2 de Qto_SpaceBaseQuantities."""
    ifc_file, metadata = ifc_with_spaces

    spaces = ifc_file.by_type("IfcSpace")
    space1 = next(s for s in spaces if s.GlobalId == metadata["space1_guid"])

    ctx = _extract_space_context(space1, ifc_file)

    assert ctx["area_m2"] == pytest.approx(4.2)


def test_extract_space_context_contained_elements_empty(ifc_with_spaces):
    """Espaço sem elementos contidos deve ter contained_elements como lista vazia."""
    ifc_file, metadata = ifc_with_spaces

    spaces = ifc_file.by_type("IfcSpace")
    space1 = next(s for s in spaces if s.GlobalId == metadata["space1_guid"])

    ctx = _extract_space_context(space1, ifc_file)

    assert isinstance(ctx["contained_elements"], list)


def test_extract_space_context_adjacent_spaces_empty(ifc_with_spaces):
    """Espaço sem IfcRelSpaceBoundary deve ter adjacent_spaces como lista vazia."""
    ifc_file, metadata = ifc_with_spaces

    spaces = ifc_file.by_type("IfcSpace")
    space1 = next(s for s in spaces if s.GlobalId == metadata["space1_guid"])

    ctx = _extract_space_context(space1, ifc_file)

    assert ctx["adjacent_spaces"] == []


# ---------------------------------------------------------------------------
# contained_elements — classificação funcional
# ---------------------------------------------------------------------------


def test_contained_elements_identifies_wc(ifc_with_sanitary_space):
    """Elemento IfcSanitaryTerminal TOILETPAN deve ter functional_label='WC'."""
    ifc_file, metadata = ifc_with_sanitary_space

    ctx = _extract_space_context(metadata["space"], ifc_file)

    labels = {e["functional_label"] for e in ctx["contained_elements"]}
    assert "WC" in labels


def test_contained_elements_identifies_basin(ifc_with_sanitary_space):
    """Elemento IfcSanitaryTerminal WASHHANDBASIN deve ter functional_label='lavatório'."""
    ifc_file, metadata = ifc_with_sanitary_space

    ctx = _extract_space_context(metadata["space"], ifc_file)

    labels = {e["functional_label"] for e in ctx["contained_elements"]}
    assert "lavatório" in labels


def test_contained_elements_has_guid_and_class(ifc_with_sanitary_space):
    """Cada elemento contido deve ter guid, ifc_class, functional_label e name."""
    ifc_file, metadata = ifc_with_sanitary_space

    ctx = _extract_space_context(metadata["space"], ifc_file)

    for element in ctx["contained_elements"]:
        assert "guid" in element
        assert "ifc_class" in element
        assert "functional_label" in element
        assert "name" in element


def test_contained_elements_furnishing_label(simple_ifc_file):
    """IfcFurnishingElement deve ter functional_label iniciando com 'mobiliário:'."""
    f, base_meta = simple_ifc_file
    storey = base_meta["storey"]

    space = f.create_entity("IfcSpace", GlobalId=ifcopenshell.guid.new(), Name="Room 1", LongName="Room 1")
    f.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=storey,
        RelatedElements=[space],
    )
    sofa = f.create_entity("IfcFurnishingElement", GlobalId=ifcopenshell.guid.new(), Name="Sofá")
    f.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=space,
        RelatedElements=[sofa],
    )

    ctx = _extract_space_context(space, f)

    labels = [e["functional_label"] for e in ctx["contained_elements"]]
    # "Sofá" deve ser classificado funcionalmente, não como label genérico
    assert any("sofá" in lbl.lower() or "poltrona" in lbl.lower() for lbl in labels)


def test_classify_sanitary_terminal_via_name_fallback():
    """Classificação por nome funciona quando PredefinedType não está definido (IFC4)."""
    # IfcSanitaryTerminal só existe em IFC4
    f4 = ifcopenshell.api.run("project.create_file", version="IFC4")
    chuveiro = f4.create_entity(
        "IfcSanitaryTerminal",
        GlobalId=ifcopenshell.guid.new(),
        Name="Chuveiro Ducha",
    )

    label = _classify_sanitary_terminal(chuveiro)

    assert label == "chuveiro"


# ---------------------------------------------------------------------------
# adjacent_spaces — via IfcRelSpaceBoundary
# ---------------------------------------------------------------------------


def test_adjacent_spaces_via_boundary(ifc_with_boundary_adjacency):
    """SpaceA deve reconhecer SpaceB como adjacente via IfcRelSpaceBoundary."""
    ifc_file, metadata = ifc_with_boundary_adjacency

    ctx = _extract_space_context(metadata["space_a"], ifc_file)

    adjacent_guids = {a["guid"] for a in ctx["adjacent_spaces"]}
    assert metadata["space_b_guid"] in adjacent_guids


def test_adjacent_spaces_boundary_connection_type(ifc_with_boundary_adjacency):
    """Adjacência via IfcRelSpaceBoundary deve ter connection_type='boundary'."""
    ifc_file, metadata = ifc_with_boundary_adjacency

    ctx = _extract_space_context(metadata["space_a"], ifc_file)

    boundary_adj = [a for a in ctx["adjacent_spaces"] if a["guid"] == metadata["space_b_guid"]]
    assert len(boundary_adj) == 1
    assert boundary_adj[0]["connection_type"] == "boundary"


def test_is_on_exterior_true_when_external_boundary(ifc_with_boundary_adjacency):
    """Espaço com IfcRelSpaceBoundary EXTERNAL deve ter is_on_exterior=True."""
    ifc_file, metadata = ifc_with_boundary_adjacency

    ctx = _extract_space_context(metadata["space_a"], ifc_file)

    assert ctx["is_on_exterior"] is True


def test_is_on_exterior_false_for_internal_only(ifc_with_boundary_adjacency):
    """Espaço sem fronteira EXTERNAL deve ter is_on_exterior=False."""
    ifc_file, metadata = ifc_with_boundary_adjacency

    ctx = _extract_space_context(metadata["space_b"], ifc_file)

    assert ctx["is_on_exterior"] is False


# ---------------------------------------------------------------------------
# adjacent_spaces — fallback via porta compartilhada
# ---------------------------------------------------------------------------


def test_adjacent_spaces_via_door_fallback(ifc_with_door_adjacency):
    """Sem IfcRelSpaceBoundary, SpaceA deve reconhecer SpaceB via porta compartilhada."""
    ifc_file, metadata = ifc_with_door_adjacency

    ctx = _extract_space_context(metadata["space_a"], ifc_file)

    adjacent_guids = {a["guid"] for a in ctx["adjacent_spaces"]}
    assert metadata["space_b_guid"] in adjacent_guids


def test_adjacent_spaces_door_connection_type(ifc_with_door_adjacency):
    """Adjacência via porta deve ter connection_type='door'."""
    ifc_file, metadata = ifc_with_door_adjacency

    ctx = _extract_space_context(metadata["space_a"], ifc_file)

    door_adj = [a for a in ctx["adjacent_spaces"] if a["guid"] == metadata["space_b_guid"]]
    assert len(door_adj) == 1
    assert door_adj[0]["connection_type"] == "door"


def test_adjacent_spaces_no_duplicates(ifc_with_door_adjacency):
    """Lista de espaços adjacentes não deve conter duplicatas."""
    ifc_file, metadata = ifc_with_door_adjacency

    ctx = _extract_space_context(metadata["space_a"], ifc_file)

    guids = [a["guid"] for a in ctx["adjacent_spaces"]]
    assert len(guids) == len(set(guids))


# ---------------------------------------------------------------------------
# context — campos ausentes / modelo incompleto
# ---------------------------------------------------------------------------


def test_context_handles_missing_quantities(simple_ifc_file):
    """Espaço sem Qto_SpaceBaseQuantities deve retornar area_m2=None sem lançar exceção."""
    f, base_meta = simple_ifc_file
    storey = base_meta["storey"]

    space = f.create_entity("IfcSpace", GlobalId=ifcopenshell.guid.new(), Name="Room 1", LongName="Room 1")
    f.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=storey,
        RelatedElements=[space],
    )

    ctx = _extract_space_context(space, f)

    assert ctx["area_m2"] is None
    assert ctx["height_m"] is None
    assert ctx["perimeter_m"] is None


def test_context_always_has_required_keys(ifc_with_spaces):
    """O contexto deve sempre conter as chaves canônicas, mesmo sem dados."""
    ifc_file, metadata = ifc_with_spaces

    spaces = ifc_file.by_type("IfcSpace")
    for space in spaces:
        ctx = _extract_space_context(space, ifc_file)
        for key in ("area_m2", "height_m", "perimeter_m", "bounding_box",
                    "contained_elements", "adjacent_spaces", "is_on_exterior", "floor"):
            assert key in ctx, f"Chave '{key}' ausente no contexto do espaço {space.GlobalId}"


# ---------------------------------------------------------------------------
# IFCAnalyzer — testes de integração
# ---------------------------------------------------------------------------


from src.ifc_analyzer.analyzer import IFCAnalyzer
from src.models import DiagnosticReport, IFCElement, Issue, ReadinessProfile


def test_analyzer_loads_model(complete_test_model, tmp_path):
    """IFCAnalyzer abre o arquivo IFC e define model_name a partir do stem do path."""
    ifc_file, _ = complete_test_model
    tmp_ifc = tmp_path / "model.ifc"
    ifc_file.write(str(tmp_ifc))

    analyzer = IFCAnalyzer(str(tmp_ifc))

    assert analyzer.model_name == "model"
    assert analyzer.ifc_file is not None


def test_analyzer_analyze_returns_report(complete_test_model, tmp_path):
    """analyze() retorna DiagnosticReport com campos obrigatórios preenchidos."""
    ifc_file, _ = complete_test_model
    tmp_ifc = tmp_path / "model.ifc"
    ifc_file.write(str(tmp_ifc))

    analyzer = IFCAnalyzer(str(tmp_ifc))
    report = analyzer.analyze()

    assert isinstance(report, DiagnosticReport)
    assert report.model_name == "model"
    assert report.model_path == str(tmp_ifc)
    assert isinstance(report.total_elements, int)
    assert isinstance(report.issues, list)


def test_analyzer_deduplicates_issues(complete_test_model, tmp_path):
    """analyze() não deve retornar issues duplicados com mesmo (guid, issue_type)."""
    ifc_file, _ = complete_test_model
    tmp_ifc = tmp_path / "model.ifc"
    ifc_file.write(str(tmp_ifc))

    analyzer = IFCAnalyzer(str(tmp_ifc))
    report = analyzer.analyze()

    keys = [(i.element_guid, i.issue_type) for i in report.issues]
    assert len(keys) == len(set(keys))


def test_analyzer_get_element_returns_data(ifc_with_spaces, tmp_path):
    """get_element() retorna IFCElement correto a partir do GUID."""
    ifc_file, metadata = ifc_with_spaces
    tmp_ifc = tmp_path / "spaces.ifc"
    ifc_file.write(str(tmp_ifc))

    analyzer = IFCAnalyzer(str(tmp_ifc))
    element = analyzer.get_element(metadata["space1_guid"])

    assert element is not None
    assert isinstance(element, IFCElement)
    assert element.guid == metadata["space1_guid"]
    assert element.ifc_class == "IfcSpace"


def test_analyzer_get_model_summary(complete_test_model, tmp_path):
    """get_model_summary() retorna dict com chaves canônicas e tipos corretos."""
    ifc_file, _ = complete_test_model
    tmp_ifc = tmp_path / "model.ifc"
    ifc_file.write(str(tmp_ifc))

    analyzer = IFCAnalyzer(str(tmp_ifc))
    summary = analyzer.get_model_summary()

    for key in ("model_name", "model_path", "schema", "total_elements",
                "total_spaces", "total_walls", "total_doors", "total_windows", "total_slabs"):
        assert key in summary, f"Chave '{key}' ausente no resumo"
    assert isinstance(summary["total_elements"], int)
    assert summary["model_name"] == "model"


# ---------------------------------------------------------------------------
# IFCAnalyzer — extratores lazy e enriquecimento de contexto
# ---------------------------------------------------------------------------


def _make_analyzer(tmp_path, ifc_file: ifcopenshell.file) -> IFCAnalyzer:
    """Salva ifc_file em disco e retorna IFCAnalyzer apontando para ele."""
    path = str(tmp_path / "model.ifc")
    ifc_file.write(path)
    return IFCAnalyzer(path)


def test_get_extractor_lazy_creation(tmp_path, simple_ifc_file):
    """get_extractor cria instâncias sob demanda e reutiliza na segunda chamada."""
    from src.ifc_analyzer.extractors import QuantityExtractor

    ifc_file, _ = simple_ifc_file
    analyzer = _make_analyzer(tmp_path, ifc_file)

    assert analyzer.extractors == {}

    extractor = analyzer.get_extractor("quantities")
    assert isinstance(extractor, QuantityExtractor)
    assert "quantities" in analyzer.extractors

    # Segunda chamada retorna a mesma instância (lazy)
    extractor2 = analyzer.get_extractor("quantities")
    assert extractor is extractor2


def test_enrich_issue_context_thermal(tmp_path, ifc_with_walls):
    """enrich_issue_context adiciona dados térmicos ao contexto de issue de parede."""
    ifc_file, meta = ifc_with_walls
    analyzer = _make_analyzer(tmp_path, ifc_file)

    issue = Issue(
        element_guid=meta["wall2_guid"],  # Wall 2: IsExternal=True, ThermalTransmittance=2.48
        element_class="IfcWall",
        issue_type="pset_missing",
        severity="high",
        description="Teste enrich thermal",
    )

    enriched = analyzer.enrich_issue_context(issue, ["is_external", "thermal_transmittance", "material"])

    assert enriched.context.get("is_external") is True
    assert enriched.context.get("thermal_transmittance") == pytest.approx(2.48)
    assert "material" in enriched.context
    assert enriched.context["material"] is not None


def test_enrich_issue_context_quantities(tmp_path, simple_ifc_file):
    """enrich_issue_context adiciona dados de quantities ao contexto de issue de parede."""
    ifc_file, meta = simple_ifc_file
    storey = meta["storey"]

    wall = ifc_file.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name="Wall Qto")
    ifc_file.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=storey,
        RelatedElements=[wall],
    )
    qto = ifcopenshell.api.run("pset.add_qto", ifc_file, product=wall, name="Qto_WallBaseQuantities")
    ifcopenshell.api.run(
        "pset.edit_qto", ifc_file, qto=qto,
        properties={"Width": 0.20, "Height": 2.80, "Length": 5.0},
    )

    analyzer = _make_analyzer(tmp_path, ifc_file)

    issue = Issue(
        element_guid=wall.GlobalId,
        element_class="IfcWall",
        issue_type="quantity_missing",
        severity="medium",
        description="Teste enrich quantities",
    )

    enriched = analyzer.enrich_issue_context(issue, ["width", "height", "length"])

    assert enriched.context.get("width") == pytest.approx(0.20)
    assert enriched.context.get("height") == pytest.approx(2.80)
    assert enriched.context.get("length") == pytest.approx(5.0)


def test_analyze_for_profile_budget(tmp_path, ifc_with_walls):
    """analyze_for_profile com perfil de orçamento enriquece issues com quantidades e classificações."""
    ifc_file, _ = ifc_with_walls
    analyzer = _make_analyzer(tmp_path, ifc_file)

    profile = ReadinessProfile(
        id="budget",
        name="Orçamento",
        description="Perfil para orçamento de obra",
        required_extractors=["quantities", "classifications"],
    )

    report = analyzer.analyze_for_profile(profile)

    assert isinstance(report, DiagnosticReport)
    assert report.total_walls == 3

    wall_issues = [i for i in report.issues if i.element_class == "IfcWall"]
    assert len(wall_issues) > 0, "Deve haver issues de parede no modelo de teste"

    budget_keys = {
        "width", "height", "length", "volume",
        "net_side_area", "has_classification", "classification_code", "classification_name",
    }
    for issue in wall_issues:
        assert any(k in issue.context for k in budget_keys), (
            f"Issue {issue.element_guid[:8]} sem contexto de orçamento: {list(issue.context.keys())}"
        )


def test_analyze_for_profile_energy(tmp_path, ifc_with_walls):
    """analyze_for_profile com perfil de energia enriquece issues com dados térmicos."""
    ifc_file, _ = ifc_with_walls
    analyzer = _make_analyzer(tmp_path, ifc_file)

    profile = ReadinessProfile(
        id="energy",
        name="Simulação Energética",
        description="Perfil para simulação energética NBR 16401",
        required_extractors=["thermal"],
    )

    report = analyzer.analyze_for_profile(profile)

    assert isinstance(report, DiagnosticReport)

    wall_issues = [i for i in report.issues if i.element_class == "IfcWall"]
    assert len(wall_issues) > 0, "Deve haver issues de parede no modelo de teste"

    thermal_keys = {"is_external", "thermal_transmittance", "material", "has_insulation"}
    for issue in wall_issues:
        assert any(k in issue.context for k in thermal_keys), (
            f"Issue {issue.element_guid[:8]} sem contexto térmico: {list(issue.context.keys())}"
        )
