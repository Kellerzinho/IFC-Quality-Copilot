"""Testes para IFCWriter."""

import os

import pytest
import ifcopenshell
import ifcopenshell.util.element

from src.writer.ifc_writer import IFCWriter


# ---------------------------------------------------------------------------
# renomear_espaco
# ---------------------------------------------------------------------------

def test_renomear_espaco_success(ifc_with_spaces):
    """Renomear com novo valor válido retorna (True, valor_anterior)."""
    f, meta = ifc_with_spaces
    writer = IFCWriter(f)
    guid = meta["space1_guid"]  # LongName original: "Room 1"

    sucesso, anterior = writer.renomear_espaco(guid, "Dormitório 01")

    assert sucesso is True
    assert anterior == "Room 1"
    espaco = f.by_guid(guid)
    assert espaco.LongName == "Dormitório 01"


def test_renomear_espaco_preserves_name(ifc_with_spaces):
    """Após renomear, o atributo Name deve permanecer intacto."""
    f, meta = ifc_with_spaces
    writer = IFCWriter(f)
    guid = meta["space1_guid"]
    espaco = f.by_guid(guid)
    name_original = espaco.Name

    writer.renomear_espaco(guid, "Dormitório 01")

    assert espaco.Name == name_original


def test_renomear_espaco_invalid_guid(ifc_with_spaces):
    """GUID inexistente deve levantar ValueError."""
    f, _ = ifc_with_spaces
    writer = IFCWriter(f)

    with pytest.raises(ValueError, match="GUID não encontrado"):
        writer.renomear_espaco("0" * 22, "Qualquer Nome")


def test_renomear_espaco_not_a_space(ifc_with_walls):
    """Elemento que não é IfcSpace deve levantar TypeError."""
    f, meta = ifc_with_walls
    writer = IFCWriter(f)
    guid = meta["wall1_guid"]  # IfcWall, não IfcSpace

    with pytest.raises(TypeError, match="IfcSpace"):
        writer.renomear_espaco(guid, "Qualquer Nome")


def test_renomear_espaco_same_value_noop(ifc_with_spaces):
    """Quando LongName já é o valor desejado, retorna (False, None) sem modificar."""
    f, meta = ifc_with_spaces
    writer = IFCWriter(f)
    guid = meta["space3_guid"]  # LongName original: "Cozinha"

    sucesso, anterior = writer.renomear_espaco(guid, "Cozinha")

    assert sucesso is False
    assert anterior is None
    assert f.by_guid(guid).LongName == "Cozinha"


def test_renomear_espaco_empty_string_raises(ifc_with_spaces):
    """novo_long_name vazio deve levantar ValueError."""
    f, meta = ifc_with_spaces
    writer = IFCWriter(f)
    guid = meta["space1_guid"]

    with pytest.raises(ValueError, match="não pode ser vazio"):
        writer.renomear_espaco(guid, "")


# ---------------------------------------------------------------------------
# preencher_pset
# ---------------------------------------------------------------------------

def test_preencher_pset_creates_new_pset(ifc_with_walls):
    """Deve criar Pset_WallCommon em parede que não o possui."""
    f, meta = ifc_with_walls
    writer = IFCWriter(f)
    guid = meta["wall3_guid"]  # wall3 não tem Pset_WallCommon

    sucesso, anteriores = writer.preencher_pset(
        guid, "Pset_WallCommon", {"IsExternal": False}
    )

    assert sucesso is True
    assert anteriores == {}
    psets = ifcopenshell.util.element.get_psets(f.by_guid(guid))
    assert "Pset_WallCommon" in psets
    assert psets["Pset_WallCommon"]["IsExternal"] is False


def test_preencher_pset_updates_existing(ifc_with_walls):
    """Deve atualizar propriedade em Pset já existente."""
    f, meta = ifc_with_walls
    writer = IFCWriter(f)
    guid = meta["wall1_guid"]  # wall1 tem Pset_WallCommon com ThermalTransmittance=None

    sucesso, _ = writer.preencher_pset(
        guid, "Pset_WallCommon", {"ThermalTransmittance": 2.48}
    )

    assert sucesso is True
    psets = ifcopenshell.util.element.get_psets(f.by_guid(guid))
    assert psets["Pset_WallCommon"]["ThermalTransmittance"] == pytest.approx(2.48)


def test_preencher_pset_returns_old_values(ifc_with_walls):
    """Deve retornar valores anteriores apenas das propriedades que já existiam."""
    f, meta = ifc_with_walls
    writer = IFCWriter(f)
    guid = meta["wall2_guid"]  # wall2: IsExternal=True, ThermalTransmittance=2.48

    _, anteriores = writer.preencher_pset(
        guid, "Pset_WallCommon", {"ThermalTransmittance": 1.0, "FireRating": "60"}
    )

    # ThermalTransmittance existia; FireRating não existia
    assert "ThermalTransmittance" in anteriores
    assert anteriores["ThermalTransmittance"] == pytest.approx(2.48)
    assert "FireRating" not in anteriores


def test_preencher_pset_multiple_properties(ifc_with_walls):
    """Deve criar múltiplas propriedades em um único pset novo."""
    f, meta = ifc_with_walls
    writer = IFCWriter(f)
    guid = meta["wall3_guid"]  # sem Pset_WallCommon

    writer.preencher_pset(
        guid,
        "Pset_WallCommon",
        {"IsExternal": True, "ThermalTransmittance": 3.5, "FireRating": "REI90"},
    )

    psets = ifcopenshell.util.element.get_psets(f.by_guid(guid))
    pset = psets["Pset_WallCommon"]
    assert pset["IsExternal"] is True
    assert pset["ThermalTransmittance"] == pytest.approx(3.5)
    assert pset["FireRating"] == "REI 90"

    # Verificar tipos IFC criados
    pset_entity = f.by_id(pset["id"])
    ifc_types = {p.Name: p.NominalValue.is_a() for p in pset_entity.HasProperties}
    assert ifc_types["IsExternal"] == "IfcBoolean"
    assert ifc_types["ThermalTransmittance"] == "IfcThermalTransmittanceMeasure"
    assert ifc_types["FireRating"] == "IfcLabel"


def test_preencher_pset_coerces_decorated_numeric_and_fire_rating(ifc_with_walls):
    f, meta = ifc_with_walls
    writer = IFCWriter(f)
    guid = meta["wall3_guid"]

    writer.preencher_pset(
        guid,
        "Pset_WallCommon",
        {
            "ThermalTransmittance": "Pset_WallCommon.ThermalTransmittance = 2.50 W/(m².K)",
            "FireRating": "120min",
        },
    )

    psets = ifcopenshell.util.element.get_psets(f.by_guid(guid))
    assert psets["Pset_WallCommon"]["ThermalTransmittance"] == pytest.approx(2.5)
    assert psets["Pset_WallCommon"]["FireRating"] == "REI 120"


def test_preencher_pset_invalid_guid(ifc_with_walls):
    """GUID inexistente deve levantar ValueError."""
    f, _ = ifc_with_walls
    writer = IFCWriter(f)

    with pytest.raises(ValueError, match="GUID não encontrado"):
        writer.preencher_pset("0" * 22, "Pset_WallCommon", {"IsExternal": True})


# ---------------------------------------------------------------------------
# criar_relacao_fills
# ---------------------------------------------------------------------------

def test_criar_relacao_fills_success(ifc_with_doors):
    """Deve criar IfcRelFillsElement para porta sem vínculo com opening."""
    f, meta = ifc_with_doors
    writer = IFCWriter(f)
    # door2 não tem fills; wall2 não tem openings → cria opening + voids + fills
    door2_guid = meta["door2_guid"]
    wall2_guid = meta["wall2_guid"]

    sucesso, valor = writer.criar_relacao_fills(door2_guid, wall2_guid)

    assert sucesso is True
    assert valor is None
    door2 = f.by_guid(door2_guid)
    fills = [r for r in f.by_type("IfcRelFillsElement") if r.RelatedBuildingElement == door2]
    assert len(fills) == 1
    # O opening deve estar associado à wall2 via IfcRelVoidsElement
    opening = fills[0].RelatingOpeningElement
    voids = [r for r in f.by_type("IfcRelVoidsElement") if r.RelatedOpeningElement == opening]
    assert len(voids) == 1
    assert voids[0].RelatingBuildingElement.GlobalId == wall2_guid


def test_criar_relacao_fills_already_exists(ifc_with_doors):
    """Porta já vinculada a opening deve retornar (False, None) sem modificar."""
    f, meta = ifc_with_doors
    writer = IFCWriter(f)
    door1_guid = meta["door1_guid"]
    wall1_guid = meta["wall1_guid"]

    fills_antes = len(f.by_type("IfcRelFillsElement"))

    sucesso, valor = writer.criar_relacao_fills(door1_guid, wall1_guid)

    assert sucesso is False
    assert valor is None
    assert len(f.by_type("IfcRelFillsElement")) == fills_antes  # nenhuma rel criada


# ---------------------------------------------------------------------------
# classificar_sistema
# ---------------------------------------------------------------------------

def test_classificar_sistema_new(ifc_with_walls):
    """Deve criar IfcClassificationReference nova para elemento sem classificação."""
    f, meta = ifc_with_walls
    writer = IFCWriter(f)
    guid = meta["wall1_guid"]

    sucesso, anterior = writer.classificar_sistema(guid, "Alvenaria")

    assert sucesso is True
    assert anterior is None
    wall = f.by_guid(guid)
    rels = [
        r for r in f.by_type("IfcRelAssociatesClassification")
        if wall in r.RelatedObjects
        and r.RelatingClassification.is_a("IfcClassificationReference")
        and r.RelatingClassification.Name == "Alvenaria"
    ]
    assert len(rels) == 1


def test_classificar_sistema_update(ifc_with_walls):
    """Deve substituir classificação anterior e retornar o valor antigo."""
    f, meta = ifc_with_walls
    writer = IFCWriter(f)
    guid = meta["wall1_guid"]

    writer.classificar_sistema(guid, "Alvenaria")
    sucesso, anterior = writer.classificar_sistema(guid, "Concreto Armado")

    assert sucesso is True
    assert anterior == "Alvenaria"
    wall = f.by_guid(guid)
    # Apenas "Concreto Armado" deve existir para este elemento
    refs_para_elemento = [
        r.RelatingClassification.Name
        for r in f.by_type("IfcRelAssociatesClassification")
        if wall in r.RelatedObjects
        and r.RelatingClassification.is_a("IfcClassificationReference")
    ]
    assert refs_para_elemento == ["Concreto Armado"]


# ---------------------------------------------------------------------------
# preencher_base_quantities
# ---------------------------------------------------------------------------

def test_preencher_base_quantities_wall(ifc_with_walls):
    """Cria Qto_WallBaseQuantities em parede sem QTO existente."""
    f, meta = ifc_with_walls
    writer = IFCWriter(f)
    guid = meta["wall1_guid"]

    sucesso, anteriores = writer.preencher_base_quantities(
        guid, "Qto_WallBaseQuantities", {"NetSideArea": 8.4, "Height": 2.8}
    )

    assert sucesso is True
    assert anteriores == {}

    wall = f.by_guid(guid)
    qtys = None
    for rel in f.by_type("IfcRelDefinesByProperties"):
        if wall in rel.RelatedObjects:
            pd = rel.RelatingPropertyDefinition
            if pd.is_a("IfcElementQuantity") and pd.Name == "Qto_WallBaseQuantities":
                qtys = {q.Name: q for q in pd.Quantities}
                break

    assert qtys is not None
    assert "NetSideArea" in qtys
    assert "Height" in qtys
    assert qtys["NetSideArea"].AreaValue == pytest.approx(8.4)
    assert qtys["Height"].LengthValue == pytest.approx(2.8)


def test_preencher_base_quantities_creates_correct_types(ifc_with_walls):
    """Verifica os tipos IFC criados para cada sufixo de nome."""
    f, meta = ifc_with_walls
    writer = IFCWriter(f)
    guid = meta["wall1_guid"]

    writer.preencher_base_quantities(
        guid,
        "Qto_WallBaseQuantities",
        {"NetSideArea": 8.4, "Height": 2.8, "NetVolume": 3.2, "ElementCount": 1.0},
    )

    wall = f.by_guid(guid)
    qtys = {}
    for rel in f.by_type("IfcRelDefinesByProperties"):
        if wall in rel.RelatedObjects:
            pd = rel.RelatingPropertyDefinition
            if pd.is_a("IfcElementQuantity") and pd.Name == "Qto_WallBaseQuantities":
                qtys = {q.Name: q for q in pd.Quantities}
                break

    assert qtys["NetSideArea"].is_a() == "IfcQuantityArea"
    assert qtys["Height"].is_a() == "IfcQuantityLength"
    assert qtys["NetVolume"].is_a() == "IfcQuantityVolume"
    assert qtys["ElementCount"].is_a() == "IfcQuantityCount"


def test_preencher_base_quantities_updates_existing(ifc_with_walls):
    """Segunda chamada atualiza o valor e retorna o anterior."""
    f, meta = ifc_with_walls
    writer = IFCWriter(f)
    guid = meta["wall1_guid"]

    writer.preencher_base_quantities(guid, "Qto_WallBaseQuantities", {"NetSideArea": 8.4})
    sucesso, anteriores = writer.preencher_base_quantities(
        guid, "Qto_WallBaseQuantities", {"NetSideArea": 10.0}
    )

    assert sucesso is True
    assert "NetSideArea" in anteriores
    assert anteriores["NetSideArea"] == pytest.approx(8.4)

    wall = f.by_guid(guid)
    for rel in f.by_type("IfcRelDefinesByProperties"):
        if wall in rel.RelatedObjects:
            pd = rel.RelatingPropertyDefinition
            if pd.is_a("IfcElementQuantity") and pd.Name == "Qto_WallBaseQuantities":
                for q in pd.Quantities:
                    if q.Name == "NetSideArea":
                        assert q.AreaValue == pytest.approx(10.0)
                break


# ---------------------------------------------------------------------------
# mapear_classificacao
# ---------------------------------------------------------------------------

def test_mapear_classificacao_sinapi(ifc_with_walls):
    """Cria IfcClassificationReference SINAPI em parede sem classificação."""
    f, meta = ifc_with_walls
    writer = IFCWriter(f)
    guid = meta["wall1_guid"]

    sucesso, anterior = writer.mapear_classificacao(
        guid, "SINAPI", "87878", "Alvenaria de vedação em bloco cerâmico 14cm"
    )

    assert sucesso is True
    assert anterior is None

    wall = f.by_guid(guid)
    rels = [
        r
        for r in f.by_type("IfcRelAssociatesClassification")
        if wall in r.RelatedObjects
        and r.RelatingClassification.is_a("IfcClassificationReference")
    ]
    assert len(rels) == 1
    ref = rels[0].RelatingClassification
    assert ref.Name == "Alvenaria de vedação em bloco cerâmico 14cm"
    code = getattr(ref, "ItemReference", None) or getattr(ref, "Identification", None)
    assert code == "87878"


def test_mapear_classificacao_update_same_system(ifc_with_walls):
    """Atualiza classificação do mesmo sistema e retorna o código anterior."""
    f, meta = ifc_with_walls
    writer = IFCWriter(f)
    guid = meta["wall1_guid"]

    writer.mapear_classificacao(guid, "SINAPI", "87878", "Alvenaria 14cm")
    sucesso, anterior = writer.mapear_classificacao(guid, "SINAPI", "88888", "Alvenaria 20cm")

    assert sucesso is True
    assert anterior == "87878"

    wall = f.by_guid(guid)
    sinapi_rels = [
        r
        for r in f.by_type("IfcRelAssociatesClassification")
        if wall in r.RelatedObjects
        and r.RelatingClassification.is_a("IfcClassificationReference")
        and r.RelatingClassification.ReferencedSource is not None
        and r.RelatingClassification.ReferencedSource.Name == "SINAPI"
    ]
    assert len(sinapi_rels) == 1
    ref = sinapi_rels[0].RelatingClassification
    code = getattr(ref, "ItemReference", None) or getattr(ref, "Identification", None)
    assert code == "88888"


# ---------------------------------------------------------------------------
# associar_zona_termica
# ---------------------------------------------------------------------------

def test_associar_zona_termica_creates_zone(ifc_with_spaces):
    """Cria nova IfcZone e associa IfcSpace."""
    f, meta = ifc_with_spaces
    writer = IFCWriter(f)
    space_guid = meta["space1_guid"]

    assert len(f.by_type("IfcZone")) == 0

    sucesso, valor = writer.associar_zona_termica(space_guid, "Zona Norte", "thermal")

    assert sucesso is True
    assert valor is None

    zones = f.by_type("IfcZone")
    assert len(zones) == 1
    assert zones[0].Name == "Zona Norte"

    space = f.by_guid(space_guid)
    membros = set()
    for rel in f.by_type("IfcRelAssignsToGroup"):
        if rel.RelatingGroup == zones[0]:
            membros.update(rel.RelatedObjects)
    assert space in membros


def test_associar_zona_termica_existing_zone(ifc_with_spaces):
    """Adiciona segundo IfcSpace a zona já existente sem criar nova zona."""
    f, meta = ifc_with_spaces
    writer = IFCWriter(f)

    writer.associar_zona_termica(meta["space1_guid"], "Zona Norte")
    sucesso, valor = writer.associar_zona_termica(meta["space2_guid"], "Zona Norte")

    assert sucesso is True
    assert valor is None

    zones = [z for z in f.by_type("IfcZone") if z.Name == "Zona Norte"]
    assert len(zones) == 1

    zone = zones[0]
    space1 = f.by_guid(meta["space1_guid"])
    space2 = f.by_guid(meta["space2_guid"])

    membros = set()
    for rel in f.by_type("IfcRelAssignsToGroup"):
        if rel.RelatingGroup == zone:
            membros.update(rel.RelatedObjects)

    assert space1 in membros
    assert space2 in membros


# ---------------------------------------------------------------------------
# salvar
# ---------------------------------------------------------------------------

def test_salvar_creates_file(ifc_with_spaces, tmp_path):
    """Deve salvar o modelo IFC em disco e retornar o path absoluto."""
    f, _ = ifc_with_spaces
    writer = IFCWriter(f)
    output = str(tmp_path / "output.ifc")

    resultado = writer.salvar(output)

    assert os.path.isfile(resultado)
    assert os.path.getsize(resultado) > 0
    # Verificar que o arquivo é um IFC válido (re-abre sem erro)
    reaberto = ifcopenshell.open(resultado)
    assert len(reaberto.by_type("IfcSpace")) == 4
