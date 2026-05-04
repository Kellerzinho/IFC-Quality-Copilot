"""Testes para AssetExtractor e ClassificationExtractor."""

import pytest
import ifcopenshell
import ifcopenshell.api
import ifcopenshell.api.owner.settings
import ifcopenshell.guid

from src.ifc_analyzer.extractors.asset_extractor import AssetExtractor
from src.ifc_analyzer.extractors.classification_extractor import ClassificationExtractor


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _setup_owner(f: ifcopenshell.file) -> None:
    """Configura person/organisation/application para a API do ifcopenshell."""
    person = ifcopenshell.api.run("owner.add_person", f, identification="eng", family_name="Engineer")
    org = ifcopenshell.api.run("owner.add_organisation", f, identification="IFC", name="IFC Test")
    user = ifcopenshell.api.run("owner.add_person_and_organisation", f, person=person, organisation=org)
    app = ifcopenshell.api.run("owner.add_application", f)
    ifcopenshell.api.owner.settings.get_user = lambda ifc: user
    ifcopenshell.api.owner.settings.get_application = lambda ifc: app


def _make_base_ifc(version: str = "IFC4") -> tuple[ifcopenshell.file, ifcopenshell.entity_instance]:
    """Cria arquivo IFC com hierarquia completa e retorna (file, storey)."""
    f = ifcopenshell.api.run("project.create_file", version=version)
    _setup_owner(f)
    project = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcProject", name="Projeto Teste")
    ifcopenshell.api.run("unit.assign_unit", f)
    site = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcSite", name="Terreno")
    building = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcBuilding", name="Edificio")
    storey = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcBuildingStorey", name="Pavimento 1")
    ifcopenshell.api.run("aggregate.assign_object", f, relating_object=project, products=[site])
    ifcopenshell.api.run("aggregate.assign_object", f, relating_object=site, products=[building])
    ifcopenshell.api.run("aggregate.assign_object", f, relating_object=building, products=[storey])
    return f, storey


def _add_furnishing_with_mfr(
    f: ifcopenshell.file,
    storey: ifcopenshell.entity_instance,
    name: str,
    manufacturer: str | None = None,
    model_ref: str | None = None,
    serial: str | None = None,
    warranty: str | None = None,
) -> ifcopenshell.entity_instance:
    """Cria IfcFurnishingElement com Pset_ManufacturerTypeInformation e Pset_Warranty."""
    elem = f.create_entity("IfcFurnishingElement", GlobalId=ifcopenshell.guid.new(), Name=name)
    f.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=storey,
        RelatedElements=[elem],
    )
    if any(v is not None for v in (manufacturer, model_ref, serial)):
        pset = ifcopenshell.api.run("pset.add_pset", f, product=elem, name="Pset_ManufacturerTypeInformation")
        props: dict = {}
        if manufacturer is not None:
            props["Manufacturer"] = manufacturer
        if model_ref is not None:
            props["ModelReference"] = model_ref
        if serial is not None:
            props["SerialNumber"] = serial
        ifcopenshell.api.run("pset.edit_pset", f, pset=pset, properties=props)
    if warranty is not None:
        w_pset = ifcopenshell.api.run("pset.add_pset", f, product=elem, name="Pset_Warranty")
        ifcopenshell.api.run("pset.edit_pset", f, pset=w_pset, properties={"WarrantyDuration": warranty})
    return elem


def _add_wall_with_material(
    f: ifcopenshell.file,
    storey: ifcopenshell.entity_instance,
    name: str,
    material_name: str,
    thickness_m: float,
) -> ifcopenshell.entity_instance:
    """Cria IfcWall com camada de material simples."""
    wall = f.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name=name)
    f.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=storey,
        RelatedElements=[wall],
    )
    mat = ifcopenshell.api.run("material.add_material", f, name=material_name)
    mat_set = ifcopenshell.api.run(
        "material.add_material_set", f, name=f"{name} layers", set_type="IfcMaterialLayerSet"
    )
    layer = ifcopenshell.api.run("material.add_layer", f, layer_set=mat_set, material=mat)
    ifcopenshell.api.run("material.edit_layer", f, layer=layer, attributes={"LayerThickness": thickness_m})
    ifcopenshell.api.run(
        "material.assign_material", f, products=[wall], type="IfcMaterialLayerSetUsage", material=mat_set
    )
    return wall


def _add_classification(
    f: ifcopenshell.file,
    element: ifcopenshell.entity_instance,
    system_name: str,
    code: str,
    cls_name: str,
) -> None:
    """Associa uma IfcClassificationReference ao elemento.

    Usa args posicionais em IfcClassificationReference para compatibilidade com
    IFC2X3 (ItemReference) e IFC4 (Identification): posição 0=Location,
    posição 1=ItemReference/Identification, posição 2=Name, posição 3=ReferencedSource.
    """
    classification = f.create_entity(
        "IfcClassification",
        Name=system_name,
        Edition="1.0",
        Source="Test",
    )
    cls_ref = f.create_entity(
        "IfcClassificationReference",
        None,           # Location
        code,           # ItemReference (IFC2X3) / Identification (IFC4)
        cls_name,       # Name
        classification, # ReferencedSource
    )
    f.create_entity(
        "IfcRelAssociatesClassification",
        GlobalId=ifcopenshell.guid.new(),
        RelatedObjects=[element],
        RelatingClassification=cls_ref,
    )


# ---------------------------------------------------------------------------
# Testes: AssetExtractor
# ---------------------------------------------------------------------------

def test_asset_info_extraction():
    """extract_asset_info deve retornar fabricante, modelo e garantia de Psets padrão."""
    f, storey = _make_base_ifc()
    chair = _add_furnishing_with_mfr(
        f, storey,
        name="Cadeira Executiva",
        manufacturer="ACME Corp",
        model_ref="CE-500",
        serial="SN-00123",
        warranty="24 meses",
    )

    extractor = AssetExtractor(f)
    info = extractor.extract_asset_info(chair)

    assert info["asset_type"] == "furnishing"
    assert info["name"] == "Cadeira Executiva"
    assert info["manufacturer"] == "ACME Corp"
    assert info["model_reference"] == "CE-500"
    assert info["serial_number"] == "SN-00123"
    assert info["warranty_duration"] == "24 meses"
    assert info["floor"] == "Pavimento 1"
    # sem espaço contentor — contido diretamente no storey
    assert info["containing_space"] is None


def test_asset_info_extraction_inside_space():
    """extract_asset_info deve capturar containing_space quando ativo está em IfcSpace."""
    f, storey = _make_base_ifc()

    space = f.create_entity(
        "IfcSpace", GlobalId=ifcopenshell.guid.new(), Name="Sala", LongName="Sala de Reuniões"
    )
    f.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=storey,
        RelatedElements=[space],
    )

    chair = f.create_entity("IfcFurnishingElement", GlobalId=ifcopenshell.guid.new(), Name="Mesa")
    f.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=space,
        RelatedElements=[chair],
    )

    extractor = AssetExtractor(f)
    info = extractor.extract_asset_info(chair)

    assert info["containing_space"] == "Sala de Reuniões"


def test_unidentified_assets():
    """get_unidentified_assets deve retornar apenas ativos sem nome, fabricante e espaço."""
    f, storey = _make_base_ifc()

    # Ativo identificado: tem nome e fabricante
    identified = _add_furnishing_with_mfr(
        f, storey, name="Luminária LED", manufacturer="Osram"
    )

    # Ativo não identificado: sem nome, fabricante ou localização em espaço
    unidentified = f.create_entity(
        "IfcFurnishingElement", GlobalId=ifcopenshell.guid.new(), Name=None
    )
    f.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=storey,
        RelatedElements=[unidentified],
    )

    extractor = AssetExtractor(f)
    result = extractor.get_unidentified_assets()

    guids = [r["guid"] for r in result]
    assert identified.GlobalId not in guids
    assert unidentified.GlobalId in guids


def test_asset_inventory_includes_all_assets():
    """get_asset_inventory deve incluir todos os ativos FM do modelo."""
    f, storey = _make_base_ifc()

    chair = _add_furnishing_with_mfr(f, storey, name="Cadeira A", manufacturer="Fabricante X")
    lamp = _add_furnishing_with_mfr(f, storey, name="Luminária B")

    extractor = AssetExtractor(f)
    inventory = extractor.get_asset_inventory()

    guids = [item["guid"] for item in inventory]
    assert chair.GlobalId in guids
    assert lamp.GlobalId in guids
    # Sem duplicatas
    assert len(guids) == len(set(guids))


# ---------------------------------------------------------------------------
# Testes: ClassificationExtractor
# ---------------------------------------------------------------------------

def test_classification_extraction_with_classification():
    """extract_classification deve retornar dados completos quando há IfcRelAssociatesClassification."""
    f, storey = _make_base_ifc()
    wall = _add_wall_with_material(f, storey, "Wall 1", "Concreto 20cm", 0.20)
    _add_classification(f, wall, "Uniclass 2015", "Ss_15_10_30", "Concrete structures")

    extractor = ClassificationExtractor(f)
    info = extractor.extract_classification(wall)

    assert info["has_classification"] is True
    assert info["classification_system"] == "Uniclass 2015"
    assert info["classification_code"] == "Ss_15_10_30"
    assert info["classification_name"] == "Concrete structures"


def test_classification_extraction_without_classification():
    """extract_classification deve retornar has_classification=False para elemento sem classificação."""
    f, storey = _make_base_ifc()
    wall = _add_wall_with_material(f, storey, "Wall Sem Classif", "Drywall", 0.125)

    extractor = ClassificationExtractor(f)
    info = extractor.extract_classification(wall)

    assert info["has_classification"] is False
    assert info["classification_system"] is None
    assert info["classification_code"] is None
    assert info["classification_name"] is None


def test_unclassified_elements_default_classes():
    """get_unclassified_elements deve retornar paredes sem classificação do conjunto padrão."""
    f, storey = _make_base_ifc()

    wall_cls = _add_wall_with_material(f, storey, "Wall Classificada", "Concreto", 0.20)
    _add_classification(f, wall_cls, "Uniclass 2015", "Ss_20_10", "Walls")

    wall_no_cls = _add_wall_with_material(f, storey, "Wall Sem Classif", "Alvenaria", 0.14)

    extractor = ClassificationExtractor(f)
    result = extractor.get_unclassified_elements()

    guids = [r["guid"] for r in result]
    assert wall_cls.GlobalId not in guids
    assert wall_no_cls.GlobalId in guids


def test_unclassified_elements_target_classes_filter():
    """get_unclassified_elements deve respeitar target_classes quando informado."""
    f, storey = _make_base_ifc()

    wall = _add_wall_with_material(f, storey, "Wall A", "Concreto", 0.20)
    door = f.create_entity("IfcDoor", GlobalId=ifcopenshell.guid.new(), Name="Porta A")
    f.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=storey,
        RelatedElements=[door],
    )

    extractor = ClassificationExtractor(f)
    # Filtra apenas IfcDoor — a parede não deve aparecer
    result = extractor.get_unclassified_elements(target_classes=["IfcDoor"])

    guids = [r["guid"] for r in result]
    assert wall.GlobalId not in guids
    assert door.GlobalId in guids


@pytest.mark.parametrize("material_name,expected_category", [
    ("Concreto armado 20cm", "Estruturas de Concreto"),
    ("Bloco cerâmico 14cm", "Vedações em Alvenaria Cerâmica"),
    ("Drywall 12,5mm", "Vedações em Drywall"),
    ("EPS 50mm", "Isolamentos Térmicos"),
    ("Granito polido", "Revestimentos em Pedra"),
])
def test_suggest_classification_from_material(material_name: str, expected_category: str):
    """suggest_classification_from_material deve retornar categoria correta para cada material."""
    f, storey = _make_base_ifc()
    wall = _add_wall_with_material(f, storey, "Wall Teste", material_name, 0.20)

    extractor = ClassificationExtractor(f)
    suggestion = extractor.suggest_classification_from_material(wall)

    assert suggestion == expected_category


def test_suggest_classification_from_material_returns_none_for_unknown():
    """suggest_classification_from_material deve retornar None para material sem palavra-chave conhecida."""
    f, storey = _make_base_ifc()
    wall = _add_wall_with_material(f, storey, "Wall Exótica", "Aerogel Futurístico", 0.05)

    extractor = ClassificationExtractor(f)
    suggestion = extractor.suggest_classification_from_material(wall)

    assert suggestion is None


def test_suggest_classification_from_material_returns_none_without_material():
    """suggest_classification_from_material deve retornar None para elemento sem material associado."""
    f, storey = _make_base_ifc()
    wall = f.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name="Wall Nua")
    f.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=storey,
        RelatedElements=[wall],
    )

    extractor = ClassificationExtractor(f)
    suggestion = extractor.suggest_classification_from_material(wall)

    assert suggestion is None
