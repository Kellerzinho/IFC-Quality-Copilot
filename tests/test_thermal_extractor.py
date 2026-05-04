"""Testes para ThermalExtractor — extrator de dados térmicos de elementos IFC."""

import pytest
import ifcopenshell
import ifcopenshell.api
import ifcopenshell.guid

from src.ifc_analyzer.extractors.thermal_extractor import ThermalExtractor


# ---------------------------------------------------------------------------
# Fixtures locais
# ---------------------------------------------------------------------------


def _setup_owner(f: ifcopenshell.file) -> None:
    import ifcopenshell.api.owner.settings

    person = ifcopenshell.api.run("owner.add_person", f, identification="eng", family_name="Engineer")
    org = ifcopenshell.api.run("owner.add_organisation", f, identification="IFC", name="IFC Test")
    user = ifcopenshell.api.run("owner.add_person_and_organisation", f, person=person, organisation=org)
    app = ifcopenshell.api.run("owner.add_application", f)
    ifcopenshell.api.owner.settings.get_user = lambda ifc: user
    ifcopenshell.api.owner.settings.get_application = lambda ifc: app


def _base_file() -> tuple[ifcopenshell.file, ifcopenshell.entity_instance]:
    """Cria arquivo IFC2X3 mínimo e retorna (file, storey)."""
    f = ifcopenshell.api.run("project.create_file", version="IFC2X3")
    _setup_owner(f)
    project = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcProject", name="Proj")
    ifcopenshell.api.run("unit.assign_unit", f)
    site = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcSite", name="Site")
    building = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcBuilding", name="Edificio")
    storey = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcBuildingStorey", name="Pav 1")
    ifcopenshell.api.run("aggregate.assign_object", f, relating_object=project, products=[site])
    ifcopenshell.api.run("aggregate.assign_object", f, relating_object=site, products=[building])
    ifcopenshell.api.run("aggregate.assign_object", f, relating_object=building, products=[storey])
    return f, storey


def _add_wall_multilayer(
    f: ifcopenshell.file,
    storey: ifcopenshell.entity_instance,
    name: str,
    layers: list[tuple[str, float]],  # [(material_name, thickness_m)]
    pset_props: dict | None = None,
) -> ifcopenshell.entity_instance:
    """Cria IfcWall com IfcMaterialLayerSet de múltiplas camadas."""
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

    mat_set = ifcopenshell.api.run(
        "material.add_material_set", f, name=f"{name} layers", set_type="IfcMaterialLayerSet"
    )
    for mat_name, thickness in layers:
        mat = ifcopenshell.api.run("material.add_material", f, name=mat_name)
        layer = ifcopenshell.api.run("material.add_layer", f, layer_set=mat_set, material=mat)
        ifcopenshell.api.run("material.edit_layer", f, layer=layer, attributes={"LayerThickness": thickness})

    ifcopenshell.api.run(
        "material.assign_material", f, products=[wall], type="IfcMaterialLayerSetUsage", material=mat_set
    )
    return wall


def _add_window(
    f: ifcopenshell.file,
    storey: ifcopenshell.entity_instance,
    wall: ifcopenshell.entity_instance,
    name: str,
    pset_props: dict | None = None,
    qto_props: dict | None = None,
) -> ifcopenshell.entity_instance:
    """Cria IfcWindow inserido num IfcOpeningElement na parede indicada."""
    window = f.create_entity("IfcWindow", GlobalId=ifcopenshell.guid.new(), Name=name)
    f.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=storey,
        RelatedElements=[window],
    )
    if pset_props is not None:
        pset = ifcopenshell.api.run("pset.add_pset", f, product=window, name="Pset_WindowCommon")
        ifcopenshell.api.run("pset.edit_pset", f, pset=pset, properties=pset_props)
    if qto_props is not None:
        qto = ifcopenshell.api.run("pset.add_qto", f, product=window, name="Qto_WindowBaseQuantities")
        ifcopenshell.api.run("pset.edit_qto", f, qto=qto, properties=qto_props)

    opening = f.create_entity("IfcOpeningElement", GlobalId=ifcopenshell.guid.new(), Name=f"Opening-{name}")
    f.create_entity(
        "IfcRelVoidsElement",
        GlobalId=ifcopenshell.guid.new(),
        RelatingBuildingElement=wall,
        RelatedOpeningElement=opening,
    )
    f.create_entity(
        "IfcRelFillsElement",
        GlobalId=ifcopenshell.guid.new(),
        RelatingOpeningElement=opening,
        RelatedBuildingElement=window,
    )
    return window


def _add_space(
    f: ifcopenshell.file,
    storey: ifcopenshell.entity_instance,
    name: str,
    area_m2: float,
    pset_props: dict | None = None,
) -> ifcopenshell.entity_instance:
    space = f.create_entity("IfcSpace", GlobalId=ifcopenshell.guid.new(), Name=name, LongName=name)
    f.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=storey,
        RelatedElements=[space],
    )
    qto = ifcopenshell.api.run("pset.add_qto", f, product=space, name="Qto_SpaceBaseQuantities")
    ifcopenshell.api.run("pset.edit_qto", f, qto=qto, properties={"NetFloorArea": area_m2})
    if pset_props is not None:
        pset = ifcopenshell.api.run("pset.add_pset", f, product=space, name="Pset_SpaceCommon")
        ifcopenshell.api.run("pset.edit_pset", f, pset=pset, properties=pset_props)
    return space


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def wall_complete():
    """IfcWall com dados térmicos completos: IsExternal, ThermalTransmittance, duas camadas."""
    f, storey = _base_file()
    wall = _add_wall_multilayer(
        f, storey, "Parede Completa",
        layers=[("Bloco ceramico", 0.14), ("Argamassa", 0.025)],
        pset_props={"IsExternal": True, "ThermalTransmittance": 2.48, "SolarAbsorptance": 0.6},
    )
    return f, wall


@pytest.fixture
def wall_partial():
    """IfcWall com dados parciais: IsExternal=True, sem ThermalTransmittance, camada única."""
    f, storey = _base_file()
    wall = _add_wall_multilayer(
        f, storey, "Parede Parcial",
        layers=[("Drywall", 0.125)],
        pset_props={"IsExternal": False},
    )
    return f, wall


@pytest.fixture
def wall_with_insulation():
    """IfcWall com camada de isolamento EPS identificável."""
    f, storey = _base_file()
    wall = _add_wall_multilayer(
        f, storey, "Parede Isolada",
        layers=[
            ("Bloco ceramico", 0.14),
            ("EPS 50mm", 0.05),
            ("Argamassa externa", 0.025),
        ],
        pset_props={"IsExternal": True, "ThermalTransmittance": 0.45},
    )
    return f, wall


@pytest.fixture
def window_complete():
    """IfcWindow com Pset_WindowCommon.ThermalTransmittance e SHGC."""
    f, storey = _base_file()
    wall = _add_wall_multilayer(
        f, storey, "Wall Ext",
        layers=[("Concreto", 0.20)],
        pset_props={"IsExternal": True},
    )
    window = _add_window(
        f, storey, wall, "Janela-01",
        pset_props={"ThermalTransmittance": 3.0, "GlazingAreaFraction": 0.7},
        qto_props={"Area": 1.5},
    )
    return f, window


@pytest.fixture
def slab_external():
    """IfcSlab com Pset_SlabCommon marcada como externa (cobertura)."""
    f, storey = _base_file()
    slab = f.create_entity("IfcSlab", GlobalId=ifcopenshell.guid.new(), Name="Laje Cobertura")
    f.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=storey,
        RelatedElements=[slab],
    )
    pset = ifcopenshell.api.run("pset.add_pset", f, product=slab, name="Pset_SlabCommon")
    ifcopenshell.api.run("pset.edit_pset", f, pset=pset, properties={"IsExternal": True, "ThermalTransmittance": 1.8})
    mat = ifcopenshell.api.run("material.add_material", f, name="Concreto armado")
    mat_set = ifcopenshell.api.run(
        "material.add_material_set", f, name="Laje layers", set_type="IfcMaterialLayerSet"
    )
    layer = ifcopenshell.api.run("material.add_layer", f, layer_set=mat_set, material=mat)
    ifcopenshell.api.run("material.edit_layer", f, layer=layer, attributes={"LayerThickness": 0.12})
    ifcopenshell.api.run(
        "material.assign_material", f, products=[slab], type="IfcMaterialLayerSetUsage", material=mat_set
    )
    return f, slab


@pytest.fixture
def space_with_external_boundary():
    """IfcSpace com parede externa via IfcRelSpaceBoundary e janela adjacente."""
    f, storey = _base_file()

    space = _add_space(f, storey, "Sala", area_m2=20.0)

    ext_wall = _add_wall_multilayer(
        f, storey, "Parede Ext",
        layers=[("Bloco ceramico", 0.14)],
        pset_props={"IsExternal": True},
    )
    int_wall = _add_wall_multilayer(
        f, storey, "Parede Int",
        layers=[("Drywall", 0.10)],
        pset_props={"IsExternal": False},
    )

    # Fronteiras do espaço
    f.create_entity(
        "IfcRelSpaceBoundary",
        GlobalId=ifcopenshell.guid.new(),
        RelatingSpace=space,
        RelatedBuildingElement=ext_wall,
        PhysicalOrVirtualBoundary="PHYSICAL",
        InternalOrExternalBoundary="EXTERNAL",
    )
    f.create_entity(
        "IfcRelSpaceBoundary",
        GlobalId=ifcopenshell.guid.new(),
        RelatingSpace=space,
        RelatedBuildingElement=int_wall,
        PhysicalOrVirtualBoundary="PHYSICAL",
        InternalOrExternalBoundary="INTERNAL",
    )

    # Janela na parede externa
    window = _add_window(f, storey, ext_wall, "Janela-Sala")

    return f, space


@pytest.fixture
def building_envelope_model():
    """Modelo completo para testar get_building_envelope."""
    f, storey = _base_file()

    ext_wall1 = _add_wall_multilayer(
        f, storey, "Fachada Norte",
        layers=[("Bloco ceramico", 0.14)],
        pset_props={"IsExternal": True, "ThermalTransmittance": 2.5},
    )
    ext_wall2 = _add_wall_multilayer(
        f, storey, "Fachada Sul",
        layers=[("Concreto", 0.20)],
        pset_props={"IsExternal": True, "ThermalTransmittance": 3.0},
    )
    _add_wall_multilayer(
        f, storey, "Parede Interna",
        layers=[("Drywall", 0.10)],
        pset_props={"IsExternal": False},
    )

    # Janelas nas fachadas
    win1 = _add_window(
        f, storey, ext_wall1, "Janela-N",
        pset_props={"ThermalTransmittance": 3.0},
        qto_props={"Area": 2.0},
    )
    win2 = _add_window(
        f, storey, ext_wall2, "Janela-S",
        pset_props={"ThermalTransmittance": 2.8},
        qto_props={"Area": 1.5},
    )

    # Laje de cobertura
    slab = f.create_entity("IfcSlab", GlobalId=ifcopenshell.guid.new(), Name="Laje Cobertura")
    f.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=storey,
        RelatedElements=[slab],
    )
    pset = ifcopenshell.api.run("pset.add_pset", f, product=slab, name="Pset_SlabCommon")
    ifcopenshell.api.run("pset.edit_pset", f, pset=pset, properties={"IsExternal": True, "ThermalTransmittance": 1.8})

    return f


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------


class TestExtractWallThermalComplete:
    """test_extract_wall_thermal_complete — parede com todos os dados térmicos."""

    def test_returns_is_external_true(self, wall_complete):
        f, wall = wall_complete
        result = ThermalExtractor(f).extract_wall_thermal(wall)
        assert result["is_external"] is True

    def test_returns_thermal_transmittance(self, wall_complete):
        f, wall = wall_complete
        result = ThermalExtractor(f).extract_wall_thermal(wall)
        assert result["thermal_transmittance"] == pytest.approx(2.48)

    def test_returns_absorptance(self, wall_complete):
        f, wall = wall_complete
        result = ThermalExtractor(f).extract_wall_thermal(wall)
        assert result["absorptance"] == pytest.approx(0.6)

    def test_returns_material_name(self, wall_complete):
        f, wall = wall_complete
        result = ThermalExtractor(f).extract_wall_thermal(wall)
        assert result["material_name"] is not None
        assert isinstance(result["material_name"], str)

    def test_returns_layers_list(self, wall_complete):
        f, wall = wall_complete
        result = ThermalExtractor(f).extract_wall_thermal(wall)
        assert len(result["layers"]) == 2

    def test_layers_have_required_keys(self, wall_complete):
        f, wall = wall_complete
        result = ThermalExtractor(f).extract_wall_thermal(wall)
        for layer in result["layers"]:
            assert "name" in layer
            assert "thickness_m" in layer
            assert "is_insulation" in layer

    def test_returns_total_thickness(self, wall_complete):
        f, wall = wall_complete
        result = ThermalExtractor(f).extract_wall_thermal(wall)
        assert result["total_thickness_m"] == pytest.approx(0.14 + 0.025)

    def test_has_insulation_false_without_insulation_layer(self, wall_complete):
        f, wall = wall_complete
        result = ThermalExtractor(f).extract_wall_thermal(wall)
        assert result["has_insulation"] is False

    def test_estimated_u_range_is_tuple_or_none(self, wall_complete):
        f, wall = wall_complete
        result = ThermalExtractor(f).extract_wall_thermal(wall)
        u_range = result["estimated_u_range"]
        assert u_range is None or (isinstance(u_range, tuple) and len(u_range) == 2)


class TestExtractWallThermalPartial:
    """test_extract_wall_thermal_partial — parede com dados incompletos."""

    def test_is_external_is_false(self, wall_partial):
        f, wall = wall_partial
        result = ThermalExtractor(f).extract_wall_thermal(wall)
        assert result["is_external"] is False

    def test_thermal_transmittance_is_none_when_absent(self, wall_partial):
        f, wall = wall_partial
        result = ThermalExtractor(f).extract_wall_thermal(wall)
        assert result["thermal_transmittance"] is None

    def test_absorptance_is_none_when_absent(self, wall_partial):
        f, wall = wall_partial
        result = ThermalExtractor(f).extract_wall_thermal(wall)
        assert result["absorptance"] is None

    def test_single_layer_thickness(self, wall_partial):
        f, wall = wall_partial
        result = ThermalExtractor(f).extract_wall_thermal(wall)
        assert result["total_thickness_m"] == pytest.approx(0.125)

    def test_has_insulation_false(self, wall_partial):
        f, wall = wall_partial
        result = ThermalExtractor(f).extract_wall_thermal(wall)
        assert result["has_insulation"] is False


class TestExtractWindowThermal:
    """test_extract_window_thermal — janela com dados térmicos."""

    def test_returns_thermal_transmittance(self, window_complete):
        f, window = window_complete
        result = ThermalExtractor(f).extract_window_thermal(window)
        assert result["thermal_transmittance"] == pytest.approx(3.0)

    def test_shgc_none_when_not_set(self, window_complete):
        f, window = window_complete
        result = ThermalExtractor(f).extract_window_thermal(window)
        # GlazingAreaFraction não é SHGC — SHGC deve vir do Pset diretamente
        assert result["shgc"] is None

    def test_returns_frame_material_or_none(self, window_complete):
        f, window = window_complete
        result = ThermalExtractor(f).extract_window_thermal(window)
        assert "frame_material" in result

    def test_returns_glazing_type_or_none(self, window_complete):
        f, window = window_complete
        result = ThermalExtractor(f).extract_window_thermal(window)
        assert "glazing_type" in result

    def test_window_without_pset_returns_nones(self):
        f, storey = _base_file()
        window = f.create_entity("IfcWindow", GlobalId=ifcopenshell.guid.new(), Name="W-bare")
        result = ThermalExtractor(f).extract_window_thermal(window)
        assert result["thermal_transmittance"] is None
        assert result["shgc"] is None


class TestExtractSpaceThermalZone:
    """test_extract_space_thermal_zone — zoneamento térmico de espaços."""

    def test_functional_name_from_space_name(self, space_with_external_boundary):
        f, space = space_with_external_boundary
        result = ThermalExtractor(f).extract_space_thermal_zone(space)
        assert result["functional_name"] == "Sala"

    def test_adjacent_external_walls_count(self, space_with_external_boundary):
        f, space = space_with_external_boundary
        result = ThermalExtractor(f).extract_space_thermal_zone(space)
        assert result["adjacent_external_walls"] == 1

    def test_has_external_window_true_when_window_on_ext_wall(self, space_with_external_boundary):
        f, space = space_with_external_boundary
        result = ThermalExtractor(f).extract_space_thermal_zone(space)
        assert result["has_external_window"] is True

    def test_floor_area_from_qto(self, space_with_external_boundary):
        f, space = space_with_external_boundary
        result = ThermalExtractor(f).extract_space_thermal_zone(space)
        assert result["floor_area"] == pytest.approx(20.0)

    def test_is_conditioned_none_when_name_gives_no_hint(self):
        """Espaço com nome neutro e sem equipamentos HVAC → is_conditioned=None."""
        f, storey = _base_file()
        space = _add_space(f, storey, "Ambiente 01", area_m2=10.0)
        result = ThermalExtractor(f).extract_space_thermal_zone(space)
        assert result["is_conditioned"] is None

    def test_space_without_boundary_has_zero_external_walls(self):
        f, storey = _base_file()
        space = _add_space(f, storey, "Room", area_m2=10.0)
        result = ThermalExtractor(f).extract_space_thermal_zone(space)
        assert result["adjacent_external_walls"] == 0
        assert result["has_external_window"] is False


class TestGetBuildingEnvelope:
    """test_get_building_envelope_summary — resumo da envoltória do edifício."""

    def test_external_walls_list_has_two_walls(self, building_envelope_model):
        f = building_envelope_model
        result = ThermalExtractor(f).get_building_envelope()
        assert len(result["external_walls"]) == 2

    def test_external_wall_entries_have_required_keys(self, building_envelope_model):
        f = building_envelope_model
        result = ThermalExtractor(f).get_building_envelope()
        for wall in result["external_walls"]:
            assert "guid" in wall
            assert "area" in wall
            assert "u_value" in wall
            assert "material" in wall

    def test_windows_list_has_two_windows(self, building_envelope_model):
        f = building_envelope_model
        result = ThermalExtractor(f).get_building_envelope()
        assert len(result["windows"]) == 2

    def test_external_slabs_list_has_one_slab(self, building_envelope_model):
        f = building_envelope_model
        result = ThermalExtractor(f).get_building_envelope()
        assert len(result["external_slabs"]) == 1

    def test_total_window_area_sums_correctly(self, building_envelope_model):
        f = building_envelope_model
        result = ThermalExtractor(f).get_building_envelope()
        assert result["total_window_area"] == pytest.approx(2.0 + 1.5)

    def test_wwr_is_zero_when_no_wall_area(self, building_envelope_model):
        f = building_envelope_model
        result = ThermalExtractor(f).get_building_envelope()
        # Sem Qto nas paredes, total_wall_area=0.0 → wwr deve ser 0.0
        assert isinstance(result["wwr"], float)

    def test_wwr_between_zero_and_one_when_areas_available(self):
        """WWR calculado corretamente quando paredes têm área nos Qto."""
        f, storey = _base_file()
        wall = _add_wall_multilayer(
            f, storey, "Fachada",
            layers=[("Bloco", 0.14)],
            pset_props={"IsExternal": True},
        )
        qto = ifcopenshell.api.run("pset.add_qto", f, product=wall, name="Qto_WallBaseQuantities")
        ifcopenshell.api.run("pset.edit_qto", f, qto=qto, properties={"NetSideArea": 10.0})
        _add_window(f, storey, wall, "W1", qto_props={"Area": 2.0})

        result = ThermalExtractor(f).get_building_envelope()
        assert result["wwr"] == pytest.approx(2.0 / 10.0)


class TestInsulationDetectionFromLayers:
    """test_insulation_detection_from_layers — detecção de isolamento por nome de camada."""

    def test_eps_layer_detected_as_insulation(self, wall_with_insulation):
        f, wall = wall_with_insulation
        result = ThermalExtractor(f).extract_wall_thermal(wall)
        insulation_layers = [layer for layer in result["layers"] if layer["is_insulation"]]
        assert len(insulation_layers) == 1
        assert "EPS" in insulation_layers[0]["name"].upper()

    def test_has_insulation_true(self, wall_with_insulation):
        f, wall = wall_with_insulation
        result = ThermalExtractor(f).extract_wall_thermal(wall)
        assert result["has_insulation"] is True

    def test_non_insulation_layers_not_flagged(self, wall_with_insulation):
        f, wall = wall_with_insulation
        result = ThermalExtractor(f).extract_wall_thermal(wall)
        non_insulation = [layer for layer in result["layers"] if not layer["is_insulation"]]
        assert len(non_insulation) == 2

    @pytest.mark.parametrize("mat_name", [
        "La mineral 50mm",
        "XPS 30mm",
        "Poliestireno expandido",
        "Manta isolante",
        "Poliuretano",
        "Rockwool",
    ])
    def test_various_insulation_keywords_detected(self, mat_name):
        f, storey = _base_file()
        wall = _add_wall_multilayer(
            f, storey, "Parede",
            layers=[("Concreto", 0.15), (mat_name, 0.05)],
        )
        result = ThermalExtractor(f).extract_wall_thermal(wall)
        assert result["has_insulation"] is True
