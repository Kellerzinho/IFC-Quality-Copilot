"""Testes do QuantityExtractor — extração de BaseQuantities de elementos IFC."""

import pytest
import ifcopenshell
import ifcopenshell.api
import ifcopenshell.guid

from src.ifc_analyzer.extractors.quantity_extractor import QuantityExtractor


# ---------------------------------------------------------------------------
# Fixtures locais
# ---------------------------------------------------------------------------


@pytest.fixture
def ifc_wall_with_qto(simple_ifc_file) -> tuple[ifcopenshell.file, ifcopenshell.entity_instance]:
    """IfcWall com Qto_WallBaseQuantities completamente preenchido."""
    f, base_meta = simple_ifc_file
    storey = base_meta["storey"]

    wall = f.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name="Parede QTO")
    f.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=storey,
        RelatedElements=[wall],
    )
    qto = ifcopenshell.api.run("pset.add_qto", f, product=wall, name="Qto_WallBaseQuantities")
    ifcopenshell.api.run(
        "pset.edit_qto",
        f,
        qto=qto,
        properties={
            "NetSideArea": 12.5,
            "GrossSideArea": 14.0,
            "Width": 0.14,
            "Height": 2.8,
            "Length": 5.0,
            "NetVolume": 1.96,
        },
    )
    return f, wall


@pytest.fixture
def ifc_wall_without_qto(simple_ifc_file) -> tuple[ifcopenshell.file, ifcopenshell.entity_instance]:
    """IfcWall sem nenhum Qto definido."""
    f, base_meta = simple_ifc_file
    storey = base_meta["storey"]

    wall = f.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name="Parede Sem QTO")
    f.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=storey,
        RelatedElements=[wall],
    )
    return f, wall


@pytest.fixture
def ifc_wall_partial_qto(simple_ifc_file) -> tuple[ifcopenshell.file, ifcopenshell.entity_instance]:
    """IfcWall com Qto_WallBaseQuantities parcialmente preenchido (apenas NetSideArea e Length)."""
    f, base_meta = simple_ifc_file
    storey = base_meta["storey"]

    wall = f.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name="Parede Parcial")
    f.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=storey,
        RelatedElements=[wall],
    )
    qto = ifcopenshell.api.run("pset.add_qto", f, product=wall, name="Qto_WallBaseQuantities")
    ifcopenshell.api.run(
        "pset.edit_qto",
        f,
        qto=qto,
        properties={"NetSideArea": 10.0, "Length": 4.0},
    )
    return f, wall


@pytest.fixture
def ifc_slab_with_qto(simple_ifc_file) -> tuple[ifcopenshell.file, ifcopenshell.entity_instance]:
    """IfcSlab com Qto_SlabBaseQuantities completamente preenchido."""
    f, base_meta = simple_ifc_file
    storey = base_meta["storey"]

    slab = f.create_entity("IfcSlab", GlobalId=ifcopenshell.guid.new(), Name="Laje QTO")
    f.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=storey,
        RelatedElements=[slab],
    )
    qto = ifcopenshell.api.run("pset.add_qto", f, product=slab, name="Qto_SlabBaseQuantities")
    ifcopenshell.api.run(
        "pset.edit_qto",
        f,
        qto=qto,
        properties={
            "NetArea": 20.0,
            "GrossArea": 22.0,
            "Width": 0.20,
            "Perimeter": 18.0,
            "NetVolume": 4.0,
        },
    )
    return f, slab


@pytest.fixture
def ifc_space_with_full_qto(simple_ifc_file) -> tuple[ifcopenshell.file, ifcopenshell.entity_instance]:
    """IfcSpace com Qto_SpaceBaseQuantities contendo todos os campos."""
    f, base_meta = simple_ifc_file
    storey = base_meta["storey"]

    space = f.create_entity(
        "IfcSpace",
        GlobalId=ifcopenshell.guid.new(),
        Name="Sala",
        LongName="Sala de Reunião",
    )
    f.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=storey,
        RelatedElements=[space],
    )
    qto = ifcopenshell.api.run("pset.add_qto", f, product=space, name="Qto_SpaceBaseQuantities")
    ifcopenshell.api.run(
        "pset.edit_qto",
        f,
        qto=qto,
        properties={
            "NetFloorArea": 18.0,
            "GrossFloorArea": 20.0,
            "Height": 2.7,
            "NetVolume": 48.6,
        },
    )
    return f, space


@pytest.fixture
def ifc_unknown_element(simple_ifc_file) -> tuple[ifcopenshell.file, ifcopenshell.entity_instance]:
    """IfcFurnishingElement — classe sem extrator definido."""
    f, base_meta = simple_ifc_file
    storey = base_meta["storey"]

    furniture = f.create_entity(
        "IfcFurnishingElement", GlobalId=ifcopenshell.guid.new(), Name="Mesa"
    )
    f.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=storey,
        RelatedElements=[furniture],
    )
    return f, furniture


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------


def test_extract_wall_quantities_from_qto(ifc_wall_with_qto):
    """Valores de Qto_WallBaseQuantities são extraídos corretamente."""
    f, wall = ifc_wall_with_qto
    extractor = QuantityExtractor(f)

    result = extractor.extract_wall_quantities(wall)

    assert result["net_side_area"] == pytest.approx(12.5)
    assert result["gross_side_area"] == pytest.approx(14.0)
    assert result["width"] == pytest.approx(0.14)
    assert result["height"] == pytest.approx(2.8)
    assert result["length"] == pytest.approx(5.0)
    assert result["volume"] == pytest.approx(1.96)


def test_extract_wall_quantities_missing_qto(ifc_wall_without_qto):
    """Quando Qto_WallBaseQuantities não existe e geometria não está disponível, todos os campos são None."""
    f, wall = ifc_wall_without_qto
    extractor = QuantityExtractor(f)

    result = extractor.extract_wall_quantities(wall)

    assert set(result.keys()) == {"net_side_area", "gross_side_area", "width", "height", "length", "volume"}
    # Sem Qto e sem OCC, todos os valores devem ser None
    assert all(v is None for v in result.values())


def test_extract_slab_quantities(ifc_slab_with_qto):
    """Valores de Qto_SlabBaseQuantities são extraídos corretamente."""
    f, slab = ifc_slab_with_qto
    extractor = QuantityExtractor(f)

    result = extractor.extract_slab_quantities(slab)

    assert result["net_area"] == pytest.approx(20.0)
    assert result["gross_area"] == pytest.approx(22.0)
    assert result["width"] == pytest.approx(0.20)
    assert result["perimeter"] == pytest.approx(18.0)
    assert result["volume"] == pytest.approx(4.0)


def test_extract_space_quantities(ifc_space_with_full_qto):
    """Valores de Qto_SpaceBaseQuantities são extraídos corretamente."""
    f, space = ifc_space_with_full_qto
    extractor = QuantityExtractor(f)

    result = extractor.extract_space_quantities(space)

    assert result["net_floor_area"] == pytest.approx(18.0)
    assert result["gross_floor_area"] == pytest.approx(20.0)
    assert result["height"] == pytest.approx(2.7)
    assert result["volume"] == pytest.approx(48.6)


def test_extract_space_quantities_partial(ifc_with_spaces):
    """IfcSpace com apenas NetFloorArea retorna os demais campos como None."""
    f, meta = ifc_with_spaces
    space = meta["spaces"][0]  # space1: area 4.2 m², sem GrossFloorArea/Height/Volume
    extractor = QuantityExtractor(f)

    result = extractor.extract_space_quantities(space)

    assert result["net_floor_area"] == pytest.approx(4.2)
    assert result["gross_floor_area"] is None
    assert result["height"] is None
    assert result["volume"] is None


def test_get_missing_quantities_lists_gaps(ifc_wall_partial_qto):
    """Campos ausentes no Qto são listados por get_missing_quantities."""
    f, wall = ifc_wall_partial_qto
    extractor = QuantityExtractor(f)

    missing = extractor.get_missing_quantities(wall)

    # NetSideArea e Length estão presentes; os demais devem aparecer como faltantes
    assert "net_side_area" not in missing
    assert "length" not in missing
    assert "gross_side_area" in missing
    assert "width" in missing
    assert "height" in missing
    assert "volume" in missing


def test_get_missing_quantities_all_present(ifc_wall_with_qto):
    """Nenhum campo é listado como faltante quando todos os Qto estão preenchidos."""
    f, wall = ifc_wall_with_qto
    extractor = QuantityExtractor(f)

    missing = extractor.get_missing_quantities(wall)

    assert missing == []


def test_get_missing_quantities_unknown_class(ifc_unknown_element):
    """Classes sem expectativas definidas retornam lista vazia."""
    f, furniture = ifc_unknown_element
    extractor = QuantityExtractor(f)

    missing = extractor.get_missing_quantities(furniture)

    assert missing == []


def test_extract_all_routes_wall_correctly(ifc_wall_with_qto):
    """extract_all roteia IfcWall para extract_wall_quantities."""
    f, wall = ifc_wall_with_qto
    extractor = QuantityExtractor(f)

    result = extractor.extract_all(wall)

    assert "net_side_area" in result
    assert "length" in result
    assert result["net_side_area"] == pytest.approx(12.5)


def test_extract_all_routes_slab_correctly(ifc_slab_with_qto):
    """extract_all roteia IfcSlab para extract_slab_quantities."""
    f, slab = ifc_slab_with_qto
    extractor = QuantityExtractor(f)

    result = extractor.extract_all(slab)

    assert "net_area" in result
    assert "perimeter" in result
    assert result["net_area"] == pytest.approx(20.0)


def test_extract_all_routes_space_correctly(ifc_space_with_full_qto):
    """extract_all roteia IfcSpace para extract_space_quantities."""
    f, space = ifc_space_with_full_qto
    extractor = QuantityExtractor(f)

    result = extractor.extract_all(space)

    assert "net_floor_area" in result
    assert result["net_floor_area"] == pytest.approx(18.0)


def test_extract_all_unknown_class_returns_empty(ifc_unknown_element):
    """extract_all retorna dict vazio para classes sem extrator."""
    f, furniture = ifc_unknown_element
    extractor = QuantityExtractor(f)

    result = extractor.extract_all(furniture)

    assert result == {}


@pytest.mark.parametrize(
    "ifc_class, expected_keys",
    [
        ("IfcWall", {"net_side_area", "gross_side_area", "width", "height", "length", "volume"}),
        ("IfcSlab", {"net_area", "gross_area", "width", "perimeter", "volume"}),
        ("IfcDoor", {"area", "height", "width"}),
        ("IfcWindow", {"area", "height", "width"}),
        ("IfcSpace", {"net_floor_area", "gross_floor_area", "height", "volume"}),
    ],
)
def test_extract_returns_expected_keys(simple_ifc_file, ifc_class, expected_keys):
    """Cada extrator retorna exatamente os campos esperados para a classe."""
    f, base_meta = simple_ifc_file
    storey = base_meta["storey"]

    element = f.create_entity(ifc_class, GlobalId=ifcopenshell.guid.new(), Name="Elemento Teste")
    f.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=storey,
        RelatedElements=[element],
    )

    extractor = QuantityExtractor(f)
    result = extractor.extract_all(element)

    assert set(result.keys()) == expected_keys
