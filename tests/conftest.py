"""Fixtures compartilhadas para os testes do IFC Quality Copilot.

Todas as fixtures que envolvem arquivos IFC retornam uma tupla:
    (ifc_file, metadata)

onde `metadata` é um dict com os GUIDs e objetos criados, para uso
nas asserções dos testes.
"""

import pytest
import ifcopenshell
import ifcopenshell.api
import ifcopenshell.api.owner.settings
import ifcopenshell.guid

from src.config import get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Limpa o cache de get_settings antes de cada teste.

    Garante que mudanças de variáveis de ambiente via monkeypatch
    sejam refletidas corretamente em cada teste.
    """
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def isolate_bsdd_cache(tmp_path, monkeypatch):
    """Aponta o cache bSDD para um arquivo temporário em cada teste.

    O caminho padrão é ``data/cache/bsdd_cache.json``, que está versionado e
    fixa a condição de grounding do benchmark: um teste que instancie
    ``BSDDClient()`` sem informar ``cache_path`` reescreve esse artefato e
    torna a condição experimental irrecuperável pelo histórico.
    """
    monkeypatch.setenv("BSDD_CACHE_PATH", str(tmp_path / "bsdd_cache.json"))
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def block_real_http(monkeypatch, request):
    """Falha o teste que tentar rede real, em vez de deixá-lo sair para a internet.

    O CLAUDE.md exige que os testes nunca dependam de bSDD ou Ollama ao vivo:
    respostas de rede variam, a suíte fica lenta e um teste pode passar por
    acidente de ambiente. Testes que precisem de rede devem declarar o marker
    ``network`` explicitamente.
    """
    if request.node.get_closest_marker("network"):
        return

    import httpx

    def _recusar(self, request_obj, *args, **kwargs):
        raise RuntimeError(
            f"Teste tentou acessar a rede: {request_obj.method} {request_obj.url}. "
            "Use mock/fixture, ou marque o teste com @pytest.mark.network."
        )

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", _recusar)


# ---------------------------------------------------------------------------
# Utilitários internos
# ---------------------------------------------------------------------------

def _setup_owner(ifc_file: ifcopenshell.file) -> None:
    """Configura person/organisation/application necessários pela API do ifcopenshell."""
    person = ifcopenshell.api.run("owner.add_person", ifc_file, identification="eng", family_name="Engineer")
    org = ifcopenshell.api.run("owner.add_organisation", ifc_file, identification="IFC", name="IFC Test")
    user = ifcopenshell.api.run("owner.add_person_and_organisation", ifc_file, person=person, organisation=org)
    app = ifcopenshell.api.run("owner.add_application", ifc_file)
    ifcopenshell.api.owner.settings.get_user = lambda ifc: user
    ifcopenshell.api.owner.settings.get_application = lambda ifc: app


def _add_space(
    ifc_file: ifcopenshell.file,
    storey: ifcopenshell.entity_instance,
    name: str,
    long_name: str,
    area_m2: float,
) -> ifcopenshell.entity_instance:
    """Cria um IfcSpace, associa ao storey e adiciona Qto_SpaceBaseQuantities."""
    space = ifc_file.create_entity(
        "IfcSpace",
        GlobalId=ifcopenshell.guid.new(),
        Name=name,
        LongName=long_name,
    )
    ifc_file.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=storey,
        RelatedElements=[space],
    )
    qto = ifcopenshell.api.run("pset.add_qto", ifc_file, product=space, name="Qto_SpaceBaseQuantities")
    ifcopenshell.api.run("pset.edit_qto", ifc_file, qto=qto, properties={"NetFloorArea": area_m2})
    return space


def _add_wall_with_material(
    ifc_file: ifcopenshell.file,
    storey: ifcopenshell.entity_instance,
    name: str,
    material_name: str,
    thickness_m: float,
    pset_props: dict | None,
) -> ifcopenshell.entity_instance:
    """Cria um IfcWall com camada de material e opcionalmente Pset_WallCommon."""
    wall = ifc_file.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name=name)
    ifc_file.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=storey,
        RelatedElements=[wall],
    )

    if pset_props is not None:
        pset = ifcopenshell.api.run("pset.add_pset", ifc_file, product=wall, name="Pset_WallCommon")
        ifcopenshell.api.run("pset.edit_pset", ifc_file, pset=pset, properties=pset_props)

    mat = ifcopenshell.api.run("material.add_material", ifc_file, name=material_name)
    mat_set = ifcopenshell.api.run(
        "material.add_material_set", ifc_file, name=f"{name} layers", set_type="IfcMaterialLayerSet"
    )
    layer = ifcopenshell.api.run("material.add_layer", ifc_file, layer_set=mat_set, material=mat)
    ifcopenshell.api.run("material.edit_layer", ifc_file, layer=layer, attributes={"LayerThickness": thickness_m})
    ifcopenshell.api.run(
        "material.assign_material", ifc_file, products=[wall], type="IfcMaterialLayerSetUsage", material=mat_set
    )

    return wall


# ---------------------------------------------------------------------------
# Fixture 1: simple_ifc_file
# ---------------------------------------------------------------------------

@pytest.fixture
def simple_ifc_file() -> tuple[ifcopenshell.file, dict]:
    """Arquivo IFC2X3 mínimo com hierarquia de projeto completa.

    Retorna:
        (ifc_file, metadata) onde metadata contém os GUIDs de project,
        site, building e storey.
    """
    f = ifcopenshell.api.run("project.create_file", version="IFC2X3")
    _setup_owner(f)

    project = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcProject", name="Projeto Teste")
    ifcopenshell.api.run("unit.assign_unit", f)
    site = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcSite", name="Terreno")
    building = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcBuilding", name="Edificio")
    storey = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcBuildingStorey", name="Pavimento 1")

    ifcopenshell.api.run("aggregate.assign_object", f, relating_object=project, products=[site])
    ifcopenshell.api.run("aggregate.assign_object", f, relating_object=site, products=[building])
    ifcopenshell.api.run("aggregate.assign_object", f, relating_object=building, products=[storey])

    metadata = {
        "project_guid": project.GlobalId,
        "site_guid": site.GlobalId,
        "building_guid": building.GlobalId,
        "storey_guid": storey.GlobalId,
        "storey": storey,
    }
    return f, metadata


# ---------------------------------------------------------------------------
# Fixture 2: ifc_with_spaces
# ---------------------------------------------------------------------------

@pytest.fixture
def ifc_with_spaces(simple_ifc_file) -> tuple[ifcopenshell.file, dict]:
    """Arquivo IFC2X3 com 4 IfcSpaces de características distintas.

    Espaços:
        - Room 1: nome genérico, área 4.2 m²
        - Room 2: nome genérico, área 12.0 m²
        - Cozinha: nome funcional, área 8.5 m²
        - Room: nome genérico sem LongName, área 3.0 m²

    Retorna:
        (ifc_file, metadata) com GUIDs de cada espaço e storey.
    """
    f, base_meta = simple_ifc_file
    storey = base_meta["storey"]

    space1 = _add_space(f, storey, name="Room 1", long_name="Room 1", area_m2=4.2)
    space2 = _add_space(f, storey, name="Room 2", long_name="Room 2", area_m2=12.0)
    space3 = _add_space(f, storey, name="Cozinha", long_name="Cozinha", area_m2=8.5)
    space4 = _add_space(f, storey, name="Room", long_name="", area_m2=3.0)

    metadata = {
        **base_meta,
        "space1_guid": space1.GlobalId,
        "space2_guid": space2.GlobalId,
        "space3_guid": space3.GlobalId,
        "space4_guid": space4.GlobalId,
        "spaces": [space1, space2, space3, space4],
    }
    return f, metadata


# ---------------------------------------------------------------------------
# Fixture 3: ifc_with_walls
# ---------------------------------------------------------------------------

@pytest.fixture
def ifc_with_walls(simple_ifc_file) -> tuple[ifcopenshell.file, dict]:
    """Arquivo IFC2X3 com 3 IfcWalls com configurações de Pset e material distintas.

    Paredes:
        - Wall 1: IsExternal=True, ThermalTransmittance=None, material "Bloco cerâmico 14cm"
        - Wall 2: IsExternal=True, ThermalTransmittance=2.48, material "Concreto 20cm"
        - Wall 3: sem Pset_WallCommon, material "Drywall"

    Retorna:
        (ifc_file, metadata) com GUIDs de cada parede.
    """
    f, base_meta = simple_ifc_file
    storey = base_meta["storey"]

    wall1 = _add_wall_with_material(
        f, storey,
        name="Wall 1",
        material_name="Bloco cerâmico 14cm",
        thickness_m=0.14,
        pset_props={"IsExternal": True, "ThermalTransmittance": None},
    )
    wall2 = _add_wall_with_material(
        f, storey,
        name="Wall 2",
        material_name="Concreto 20cm",
        thickness_m=0.20,
        pset_props={"IsExternal": True, "ThermalTransmittance": 2.48},
    )
    wall3 = _add_wall_with_material(
        f, storey,
        name="Wall 3",
        material_name="Drywall",
        thickness_m=0.125,
        pset_props=None,  # sem Pset_WallCommon
    )

    metadata = {
        **base_meta,
        "wall1_guid": wall1.GlobalId,
        "wall2_guid": wall2.GlobalId,
        "wall3_guid": wall3.GlobalId,
        "walls": [wall1, wall2, wall3],
        "wall1": wall1,
        "wall2": wall2,
        "wall3": wall3,
    }
    return f, metadata


# ---------------------------------------------------------------------------
# Fixture 4: ifc_with_doors
# ---------------------------------------------------------------------------

@pytest.fixture
def ifc_with_doors(ifc_with_walls) -> tuple[ifcopenshell.file, dict]:
    """Arquivo IFC2X3 com 2 IfcDoors: uma com IfcRelFillsElement, outra sem.

    Portas:
        - Door 1: relacionada a Wall 1 via IfcRelFillsElement (relação OK)
        - Door 2: sem IfcRelFillsElement (relação quebrada)

    Retorna:
        (ifc_file, metadata) com GUIDs de cada porta e opening.
    """
    f, base_meta = ifc_with_walls
    storey = base_meta["storey"]

    # Door 1 — com IfcRelFillsElement via IfcOpeningElement em Wall 1
    door1 = f.create_entity("IfcDoor", GlobalId=ifcopenshell.guid.new(), Name="Door 1")
    f.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=storey,
        RelatedElements=[door1],
    )
    opening1 = f.create_entity("IfcOpeningElement", GlobalId=ifcopenshell.guid.new(), Name="Opening 1")
    f.create_entity(
        "IfcRelVoidsElement",
        GlobalId=ifcopenshell.guid.new(),
        RelatingBuildingElement=base_meta["wall1"],
        RelatedOpeningElement=opening1,
    )
    f.create_entity(
        "IfcRelFillsElement",
        GlobalId=ifcopenshell.guid.new(),
        RelatingOpeningElement=opening1,
        RelatedBuildingElement=door1,
    )

    # Door 2 — sem IfcRelFillsElement (relação quebrada)
    door2 = f.create_entity("IfcDoor", GlobalId=ifcopenshell.guid.new(), Name="Door 2")
    f.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=storey,
        RelatedElements=[door2],
    )

    metadata = {
        **base_meta,
        "door1_guid": door1.GlobalId,
        "door2_guid": door2.GlobalId,
        "opening1_guid": opening1.GlobalId,
        "doors": [door1, door2],
        "door1": door1,
        "door2": door2,
    }
    return f, metadata


# ---------------------------------------------------------------------------
# Fixture 5: complete_test_model
# ---------------------------------------------------------------------------

@pytest.fixture
def complete_test_model(simple_ifc_file) -> tuple[ifcopenshell.file, dict]:
    """Modelo IFC2X3 completo para testes de integração.

    Combina espaços, paredes, portas e uma laje sem LoadBearing.
    Projetado para exercitar todos os tipos de Issue do diagnóstico.

    Retorna:
        (ifc_file, metadata) com GUIDs de todos os elementos criados.
    """
    f, base_meta = simple_ifc_file
    storey = base_meta["storey"]

    # --- Espaços ---
    space1 = _add_space(f, storey, name="Room 1", long_name="Room 1", area_m2=4.2)
    space2 = _add_space(f, storey, name="Cozinha", long_name="Cozinha", area_m2=8.5)

    # --- Paredes ---
    wall1 = _add_wall_with_material(
        f, storey,
        name="Wall 1",
        material_name="Bloco cerâmico 14cm",
        thickness_m=0.14,
        pset_props={"IsExternal": True, "ThermalTransmittance": None},  # issue: pset_missing
    )
    wall2 = _add_wall_with_material(
        f, storey,
        name="Wall 2",
        material_name="Concreto 20cm",
        thickness_m=0.20,
        pset_props={"IsExternal": True, "ThermalTransmittance": 2.48},  # OK
    )
    wall3 = _add_wall_with_material(
        f, storey,
        name="Wall 3",
        material_name="Drywall",
        thickness_m=0.125,
        pset_props=None,  # issue: pset_missing (sem pset algum)
    )

    # --- Porta com relação OK ---
    door1 = f.create_entity("IfcDoor", GlobalId=ifcopenshell.guid.new(), Name="Door 1")
    f.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=storey,
        RelatedElements=[door1],
    )
    opening1 = f.create_entity("IfcOpeningElement", GlobalId=ifcopenshell.guid.new(), Name="Opening 1")
    f.create_entity(
        "IfcRelVoidsElement",
        GlobalId=ifcopenshell.guid.new(),
        RelatingBuildingElement=wall1,
        RelatedOpeningElement=opening1,
    )
    f.create_entity(
        "IfcRelFillsElement",
        GlobalId=ifcopenshell.guid.new(),
        RelatingOpeningElement=opening1,
        RelatedBuildingElement=door1,
    )

    # --- Porta sem relação (issue: relation_broken) ---
    door2 = f.create_entity("IfcDoor", GlobalId=ifcopenshell.guid.new(), Name="Door 2")
    f.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=storey,
        RelatedElements=[door2],
    )

    # --- Laje sem Pset_SlabCommon.LoadBearing (issue: pset_missing) ---
    slab = f.create_entity("IfcSlab", GlobalId=ifcopenshell.guid.new(), Name="Laje Tipo")
    f.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=storey,
        RelatedElements=[slab],
    )

    metadata = {
        **base_meta,
        # espaços
        "space1_guid": space1.GlobalId,
        "space2_guid": space2.GlobalId,
        "spaces": [space1, space2],
        # paredes
        "wall1_guid": wall1.GlobalId,
        "wall2_guid": wall2.GlobalId,
        "wall3_guid": wall3.GlobalId,
        "walls": [wall1, wall2, wall3],
        "wall1": wall1,
        # portas
        "door1_guid": door1.GlobalId,
        "door2_guid": door2.GlobalId,
        "doors": [door1, door2],
        # laje
        "slab_guid": slab.GlobalId,
        "slab": slab,
    }
    return f, metadata


# ---------------------------------------------------------------------------
# Fixture 6: simple_ifc_file_ifc4  (base IFC4, necessário para IfcSanitaryTerminal)
# ---------------------------------------------------------------------------

@pytest.fixture
def simple_ifc_file_ifc4() -> tuple[ifcopenshell.file, dict]:
    """Arquivo IFC4 mínimo com hierarquia de projeto completa.

    Idêntico ao simple_ifc_file, mas no schema IFC4, que contém
    IfcSanitaryTerminal e outros tipos ausentes no IFC2X3.

    Retorna:
        (ifc_file, metadata) com project, site, building e storey.
    """
    f = ifcopenshell.api.run("project.create_file", version="IFC4")
    _setup_owner(f)

    project = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcProject", name="Projeto Teste IFC4")
    ifcopenshell.api.run("unit.assign_unit", f)
    site = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcSite", name="Terreno")
    building = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcBuilding", name="Edificio")
    storey = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcBuildingStorey", name="Pavimento 1")

    ifcopenshell.api.run("aggregate.assign_object", f, relating_object=project, products=[site])
    ifcopenshell.api.run("aggregate.assign_object", f, relating_object=site, products=[building])
    ifcopenshell.api.run("aggregate.assign_object", f, relating_object=building, products=[storey])

    metadata = {
        "project_guid": project.GlobalId,
        "site_guid": site.GlobalId,
        "building_guid": building.GlobalId,
        "storey_guid": storey.GlobalId,
        "storey": storey,
    }
    return f, metadata


# ---------------------------------------------------------------------------
# Fixture 7: ifc_with_sanitary_space
# ---------------------------------------------------------------------------

@pytest.fixture
def ifc_with_sanitary_space(simple_ifc_file_ifc4) -> tuple[ifcopenshell.file, dict]:
    """Arquivo IFC2X3 com IfcSpace genérico contendo terminais sanitários.

    Espaço:
        - Room 1: nome genérico, área 6.0 m²
          - WC (IfcSanitaryTerminal, SanitaryTerminalType=TOILETPAN)
          - Lavatório (IfcSanitaryTerminal, SanitaryTerminalType=WASHHANDBASIN)

    Retorna:
        (ifc_file, metadata) com GUIDs do espaço e terminais.
    """
    f, base_meta = simple_ifc_file_ifc4
    storey = base_meta["storey"]

    space = f.create_entity(
        "IfcSpace",
        GlobalId=ifcopenshell.guid.new(),
        Name="Room 1",
        LongName="Room 1",
    )
    f.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=storey,
        RelatedElements=[space],
    )
    qto = ifcopenshell.api.run("pset.add_qto", f, product=space, name="Qto_SpaceBaseQuantities")
    ifcopenshell.api.run("pset.edit_qto", f, qto=qto, properties={"NetFloorArea": 6.0})

    wc = f.create_entity(
        "IfcSanitaryTerminal",
        GlobalId=ifcopenshell.guid.new(),
        Name="WC-01",
        PredefinedType="TOILETPAN",
    )
    basin = f.create_entity(
        "IfcSanitaryTerminal",
        GlobalId=ifcopenshell.guid.new(),
        Name="Lav-01",
        PredefinedType="WASHHANDBASIN",
    )
    f.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=space,
        RelatedElements=[wc, basin],
    )

    metadata = {
        **base_meta,
        "space": space,
        "space_guid": space.GlobalId,
        "wc": wc,
        "wc_guid": wc.GlobalId,
        "basin": basin,
        "basin_guid": basin.GlobalId,
    }
    return f, metadata


# ---------------------------------------------------------------------------
# Fixture 8: ifc_with_boundary_adjacency
# ---------------------------------------------------------------------------

@pytest.fixture
def ifc_with_boundary_adjacency(simple_ifc_file) -> tuple[ifcopenshell.file, dict]:
    """Arquivo IFC2X3 com dois IfcSpaces adjacentes via IfcRelSpaceBoundary.

    Topologia:
        - SpaceA (Room 1) e SpaceB (Room 2) compartilham Wall via IfcRelSpaceBoundary
        - SpaceA tem uma fronteira marcada como EXTERNAL (para testar is_on_exterior)

    Retorna:
        (ifc_file, metadata) com GUIDs dos espaços e da parede.
    """
    f, base_meta = simple_ifc_file
    storey = base_meta["storey"]

    space_a = f.create_entity(
        "IfcSpace", GlobalId=ifcopenshell.guid.new(), Name="Room 1", LongName="Room 1"
    )
    space_b = f.create_entity(
        "IfcSpace", GlobalId=ifcopenshell.guid.new(), Name="Room 2", LongName="Room 2"
    )
    for sp in (space_a, space_b):
        f.create_entity(
            "IfcRelContainedInSpatialStructure",
            GlobalId=ifcopenshell.guid.new(),
            RelatingStructure=storey,
            RelatedElements=[sp],
        )

    shared_wall = f.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name="Wall Shared")
    ext_wall = f.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name="Wall Exterior")

    # Fronteira interna compartilhada entre SpaceA e SpaceB
    f.create_entity(
        "IfcRelSpaceBoundary",
        GlobalId=ifcopenshell.guid.new(),
        RelatingSpace=space_a,
        RelatedBuildingElement=shared_wall,
        PhysicalOrVirtualBoundary="PHYSICAL",
        InternalOrExternalBoundary="INTERNAL",
    )
    f.create_entity(
        "IfcRelSpaceBoundary",
        GlobalId=ifcopenshell.guid.new(),
        RelatingSpace=space_b,
        RelatedBuildingElement=shared_wall,
        PhysicalOrVirtualBoundary="PHYSICAL",
        InternalOrExternalBoundary="INTERNAL",
    )
    # Fronteira externa para SpaceA
    f.create_entity(
        "IfcRelSpaceBoundary",
        GlobalId=ifcopenshell.guid.new(),
        RelatingSpace=space_a,
        RelatedBuildingElement=ext_wall,
        PhysicalOrVirtualBoundary="PHYSICAL",
        InternalOrExternalBoundary="EXTERNAL",
    )

    metadata = {
        **base_meta,
        "space_a": space_a,
        "space_a_guid": space_a.GlobalId,
        "space_b": space_b,
        "space_b_guid": space_b.GlobalId,
        "shared_wall": shared_wall,
        "ext_wall": ext_wall,
    }
    return f, metadata


# ---------------------------------------------------------------------------
# Fixture 9: ifc_with_door_adjacency
# ---------------------------------------------------------------------------

@pytest.fixture
def ifc_with_door_adjacency(simple_ifc_file) -> tuple[ifcopenshell.file, dict]:
    """Arquivo IFC2X3 com dois IfcSpaces adjacentes via porta compartilhada.

    Topologia (sem IfcRelSpaceBoundary):
        - SpaceA (Room 1) e SpaceB (Room 2) ambos contêm a mesma Door 1
          via IfcRelContainedInSpatialStructure, indicando adjacência.

    Retorna:
        (ifc_file, metadata) com GUIDs dos espaços e da porta.
    """
    f, base_meta = simple_ifc_file
    storey = base_meta["storey"]

    space_a = f.create_entity(
        "IfcSpace", GlobalId=ifcopenshell.guid.new(), Name="Room 1", LongName="Room 1"
    )
    space_b = f.create_entity(
        "IfcSpace", GlobalId=ifcopenshell.guid.new(), Name="Room 2", LongName="Room 2"
    )
    for sp in (space_a, space_b):
        f.create_entity(
            "IfcRelContainedInSpatialStructure",
            GlobalId=ifcopenshell.guid.new(),
            RelatingStructure=storey,
            RelatedElements=[sp],
        )

    shared_door = f.create_entity("IfcDoor", GlobalId=ifcopenshell.guid.new(), Name="Door 1")

    # Mesma porta contida nos dois espaços
    f.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=space_a,
        RelatedElements=[shared_door],
    )
    f.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=space_b,
        RelatedElements=[shared_door],
    )

    metadata = {
        **base_meta,
        "space_a": space_a,
        "space_a_guid": space_a.GlobalId,
        "space_b": space_b,
        "space_b_guid": space_b.GlobalId,
        "shared_door": shared_door,
        "shared_door_guid": shared_door.GlobalId,
    }
    return f, metadata
