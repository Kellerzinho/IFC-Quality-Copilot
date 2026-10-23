"""Testes do inventário de propriedades (scripts/mapear_propriedades.py).

Todos os IFC são sintéticos e gerados no próprio teste; nenhum modelo real é lido.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.api.owner.settings as owner_settings
import ifcopenshell.guid
import pytest

from scripts import mapear_propriedades as mp


def _owner_user(ifc: ifcopenshell.file) -> ifcopenshell.entity_instance | None:
    """Usuário sintético só no IFC2X3, onde IfcOwnerHistory é obrigatório."""
    if ifc.schema != "IFC2X3":
        return None
    existing = ifc.by_type("IfcPersonAndOrganization")
    if existing:
        return existing[0]
    return ifc.create_entity(
        "IfcPersonAndOrganization",
        ThePerson=ifc.create_entity("IfcPerson", FamilyName="Teste"),
        TheOrganization=ifc.create_entity("IfcOrganization", Name="Teste"),
    )


def _owner_application(ifc: ifcopenshell.file) -> ifcopenshell.entity_instance | None:
    """Aplicação sintética só no IFC2X3."""
    user = _owner_user(ifc)
    if user is None:
        return None
    existing = ifc.by_type("IfcApplication")
    if existing:
        return existing[0]
    return ifc.create_entity(
        "IfcApplication",
        ApplicationDeveloper=user.TheOrganization,
        Version="0",
        ApplicationFullName="teste",
        ApplicationIdentifier="teste",
    )


@pytest.fixture(autouse=True)
def _owner_history_sintetico(monkeypatch: pytest.MonkeyPatch) -> None:
    """IFC2X3 exige IfcOwnerHistory na API; IFC4 fica sem dono."""
    monkeypatch.setattr(owner_settings, "get_user", _owner_user)
    monkeypatch.setattr(owner_settings, "get_application", _owner_application)


def _new_file(schema: str, units: tuple[str, ...] = ("LENGTHUNIT",)) -> ifcopenshell.file:
    """IFC mínimo com projeto e as unidades SI pedidas."""
    f = ifcopenshell.api.run("project.create_file", version=schema)
    ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcProject", name="Projeto sintético")
    assigned = [ifcopenshell.api.run("unit.add_si_unit", f, unit_type=u) for u in units]
    ifcopenshell.api.run("unit.assign_unit", f, units=assigned)
    return f


def _element(f: ifcopenshell.file, ifc_class: str, name: str) -> ifcopenshell.entity_instance:
    return ifcopenshell.api.run("root.create_entity", f, ifc_class=ifc_class, name=name)


def _prop(
    f: ifcopenshell.file,
    name: str,
    measure: str,
    value: object,
    unit: ifcopenshell.entity_instance | None = None,
) -> ifcopenshell.entity_instance:
    return f.create_entity(
        "IfcPropertySingleValue", Name=name, NominalValue=f.create_entity(measure, value), Unit=unit
    )


def _pset(
    f: ifcopenshell.file,
    element: ifcopenshell.entity_instance,
    name: str,
    *props: ifcopenshell.entity_instance,
) -> ifcopenshell.entity_instance:
    pset = f.create_entity(
        "IfcPropertySet", GlobalId=ifcopenshell.guid.new(), Name=name, HasProperties=list(props)
    )
    f.create_entity(
        "IfcRelDefinesByProperties",
        GlobalId=ifcopenshell.guid.new(),
        RelatedObjects=[element],
        RelatingPropertyDefinition=pset,
    )
    return pset


def _set_exporter(f: ifcopenshell.file, system: str, app_name: str, version: str) -> None:
    f.header.file_name.originating_system = system
    org = f.create_entity("IfcOrganization", Name="Fornecedor sintético")
    f.create_entity(
        "IfcApplication",
        ApplicationDeveloper=org,
        Version=version,
        ApplicationFullName=app_name,
        ApplicationIdentifier=app_name,
    )


def _save(f: ifcopenshell.file, tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    f.write(str(path))
    return path


def _rows(rows: list[dict[str, object]], **filters: object) -> list[dict[str, object]]:
    return [r for r in rows if all(r[k] == v for k, v in filters.items())]


@pytest.mark.parametrize(
    ("system", "app", "version"),
    [("Autodesk Revit 2026", "Revit", "26.2"), ("ArchiCAD 27", "ARCHICAD", "27.0")],
)
def test_software_de_origem_identifica_o_exportador(
    tmp_path: Path, system: str, app: str, version: str
) -> None:
    f = _new_file("IFC4")
    wall = _element(f, "IfcWall", "W1")
    _pset(f, wall, "Pset_WallCommon", _prop(f, "IsExternal", "IfcBoolean", True))
    _set_exporter(f, system, app, version)

    info, rows = mp.map_file(_save(f, tmp_path, "m.ifc"), ["IfcWall"])

    # O IfcOpenShell grava a si mesmo como preprocessor_version ao salvar.
    partes = str(info["software"]).split(" | ")
    assert partes[0] == system
    assert f"{app} {version}" in partes
    assert {r["software"] for r in rows} == {info["software"]}


def test_mesmo_caminho_em_dois_exportadores_aparece_na_matriz(tmp_path: Path) -> None:
    paths = []
    for name, pset in (("revit.ifc", "Pset_WallCommon"), ("archicad.ifc", "ArchiCADProperties")):
        f = _new_file("IFC4")
        _pset(f, _element(f, "IfcWall", "W1"), pset, _prop(f, "FireRating", "IfcLabel", "EI 60"))
        paths.append(_save(f, tmp_path, name))
    manifest, rows = [], []
    for path in paths:
        info, file_rows = mp.map_file(path, ["IfcWall"])
        manifest.append(info)
        rows += file_rows

    mp.write_outputs(tmp_path / "out", manifest, rows, ["fire"])

    with (tmp_path / "out" / "matriz_softwares.csv").open(encoding="utf-8-sig") as handle:
        matriz = list(csv.reader(handle))
    assert matriz[0] == ["classe", "caminho", "revit.ifc", "archicad.ifc"]
    assert ["IfcWall", "Pset_WallCommon.FireRating", "100.0", ""] in matriz
    assert ["IfcWall", "ArchiCADProperties.FireRating", "", "100.0"] in matriz


@pytest.mark.parametrize(
    ("units", "esperado_pressao"),
    [
        (("LENGTHUNIT", "PRESSUREUNIT"), ("PASCAL", "projeto")),
        (("LENGTHUNIT",), ("", "ausente")),
    ],
)
def test_ifcreal_sem_unidade_e_ifcpressuremeasure_nao_se_misturam(
    tmp_path: Path, units: tuple[str, ...], esperado_pressao: tuple[str, str]
) -> None:
    f = _new_file("IFC4", units)
    c1, c2 = _element(f, "IfcColumn", "C1"), _element(f, "IfcColumn", "C2")
    _pset(f, c1, "Dados_Concreto", _prop(f, "fck", "IfcReal", 30.0))
    _pset(f, c2, "Dados_Concreto", _prop(f, "fck", "IfcPressureMeasure", 30e6))

    _, rows = mp.map_file(_save(f, tmp_path, "m.ifc"), ["IfcColumn"])

    fck = _rows(rows, propriedade="fck")
    assert len(fck) == 2, "tipos diferentes no mesmo caminho precisam ficar em linhas separadas"
    real = _rows(fck, tipo_valor="IfcReal")[0]
    pressao = _rows(fck, tipo_valor="IfcPressureMeasure")[0]
    assert (real["unidade"], real["unidade_origem"]) == ("", "adimensional")
    assert (pressao["unidade"], pressao["unidade_origem"]) == esperado_pressao
    assert real["elementos_com"] == pressao["elementos_com"] == 1
    assert real["cobertura_pct"] == pressao["cobertura_pct"] == 50.0


def test_unidade_explicita_prevalece_sobre_a_do_projeto(tmp_path: Path) -> None:
    f = _new_file("IFC4", ("LENGTHUNIT", "PRESSUREUNIT"))
    mpa = f.create_entity("IfcSIUnit", UnitType="PRESSUREUNIT", Prefix="MEGA", Name="PASCAL")
    _pset(
        f, _element(f, "IfcColumn", "C1"), "Dados", _prop(f, "fck", "IfcPressureMeasure", 30.0, mpa)
    )

    _, rows = mp.map_file(_save(f, tmp_path, "m.ifc"), ["IfcColumn"])

    assert (rows[0]["unidade"], rows[0]["unidade_origem"]) == ("MEGAPASCAL", "explicita")


def test_pset_de_tipo_e_de_ocorrencia_tem_origens_separadas(tmp_path: Path) -> None:
    f = _new_file("IFC4")
    column = _element(f, "IfcColumn", "C1")
    column_type = _element(f, "IfcColumnType", "Pilar 30x30")
    ifcopenshell.api.run("type.assign_type", f, related_objects=[column], relating_type=column_type)
    type_pset = f.create_entity(
        "IfcPropertySet",
        GlobalId=ifcopenshell.guid.new(),
        Name="Pset_ColumnCommon",
        HasProperties=[_prop(f, "LoadBearing", "IfcBoolean", True)],
    )
    column_type.HasPropertySets = [type_pset]
    _pset(f, column, "Pset_ColumnCommon", _prop(f, "LoadBearing", "IfcBoolean", False))

    _, rows = mp.map_file(_save(f, tmp_path, "m.ifc"), ["IfcColumn"])

    load_bearing = _rows(rows, propriedade="LoadBearing")
    assert {r["origem"] for r in load_bearing} == {"tipo", "ocorrencia"}
    assert _rows(load_bearing, origem="tipo")[0]["exemplos"] == "True"
    assert _rows(load_bearing, origem="ocorrencia")[0]["exemplos"] == "False"


def _concrete_material(
    f: ifcopenshell.file, element: ifcopenshell.entity_instance
) -> ifcopenshell.entity_instance:
    material = ifcopenshell.api.run("material.add_material", f, name="Concreto C30")
    ifcopenshell.api.run("material.assign_material", f, products=[element], material=material)
    return material


def test_propriedades_de_material_ifc4(tmp_path: Path) -> None:
    f = _new_file("IFC4", ("LENGTHUNIT", "PRESSUREUNIT"))
    column = _element(f, "IfcColumn", "C1")
    material = _concrete_material(f, column)
    f.create_entity(
        "IfcMaterialProperties",
        Name="Pset_MaterialConcrete",
        Material=material,
        Properties=[_prop(f, "CompressiveStrength", "IfcPressureMeasure", 30e6)],
    )

    _, rows = mp.map_file(_save(f, tmp_path, "m.ifc"), ["IfcColumn"])

    strength = _rows(rows, origem="material", pset="Pset_MaterialConcrete")[0]
    assert strength["propriedade"] == "CompressiveStrength"
    assert strength["unidade_origem"] == "projeto"
    nome = _rows(rows, pset=mp.MATERIAL_NAME_PSET)[0]
    assert nome["exemplos"] == "Concreto C30"


def test_propriedades_de_material_ifc2x3_estendidas_e_tipadas(tmp_path: Path) -> None:
    f = _new_file("IFC2X3", ("LENGTHUNIT", "PRESSUREUNIT"))
    column = _element(f, "IfcColumn", "C1")
    material = _concrete_material(f, column)
    f.create_entity(
        "IfcExtendedMaterialProperties",
        Material=material,
        Name="Dados_Concreto",
        ExtendedProperties=[_prop(f, "Cobrimento", "IfcPositiveLengthMeasure", 0.03)],
    )
    f.create_entity(
        "IfcMechanicalConcreteMaterialProperties", Material=material, CompressiveStrength=30e6
    )

    _, rows = mp.map_file(_save(f, tmp_path, "m.ifc"), ["IfcColumn"])

    cobrimento = _rows(rows, pset="Dados_Concreto", propriedade="Cobrimento")[0]
    assert (cobrimento["origem"], cobrimento["unidade_origem"]) == ("material", "projeto")
    tipada = _rows(
        rows, pset="IfcMechanicalConcreteMaterialProperties", propriedade="CompressiveStrength"
    )[0]
    assert tipada["tipo_valor"] == "IfcPressureMeasure"
    assert tipada["unidade_origem"] == "projeto"
    assert tipada["exemplos"] == "30000000.0"


def test_classe_ausente_no_schema_e_registrada_sem_interromper(tmp_path: Path) -> None:
    f = _new_file("IFC2X3")
    _pset(
        f,
        _element(f, "IfcWall", "W1"),
        "Pset_WallCommon",
        _prop(f, "IsExternal", "IfcBoolean", True),
    )

    info, rows = mp.map_file(_save(f, tmp_path, "m.ifc"), ["IfcChimney", "IfcWall"])

    assert info["classes_ausentes_no_schema"] == ["IfcChimney"]
    assert info["elementos_por_classe"] == {"IfcWall": 1}
    assert _rows(rows, classe="IfcWall", propriedade="IsExternal")


@pytest.mark.parametrize("com_unidade_derivada", [True, False])
def test_unidade_derivada_nao_e_tratada_como_adimensional(
    tmp_path: Path, com_unidade_derivada: bool
) -> None:
    f = _new_file("IFC2X3", ("LENGTHUNIT", "POWERUNIT"))
    if com_unidade_derivada:
        metre, watt = f.by_type("IfcSIUnit")
        u_unit = f.create_entity(
            "IfcDerivedUnit",
            Elements=[
                f.create_entity("IfcDerivedUnitElement", Unit=watt, Exponent=1),
                f.create_entity("IfcDerivedUnitElement", Unit=metre, Exponent=-2),
            ],
            UnitType="THERMALTRANSMITTANCEUNIT",
        )
        assignment = f.by_type("IfcUnitAssignment")[0]
        assignment.Units = [*assignment.Units, u_unit]
    wall = _element(f, "IfcWall", "W1")
    _pset(
        f,
        wall,
        "Pset_WallCommon",
        _prop(f, "ThermalTransmittance", "IfcThermalTransmittanceMeasure", 2.3),
    )

    _, rows = mp.map_file(_save(f, tmp_path, "m.ifc"), ["IfcWall"])

    u_row = _rows(rows, propriedade="ThermalTransmittance")[0]
    if com_unidade_derivada:
        assert (u_row["unidade"], u_row["unidade_origem"]) == ("WATT·METRE^-2", "projeto")
    else:
        assert (u_row["unidade"], u_row["unidade_origem"]) == ("", "ausente")


def test_todas_as_classes_usa_classe_concreta_sem_contar_subtipo_duas_vezes(
    tmp_path: Path,
) -> None:
    f = _new_file("IFC4")
    for ifc_class, name in (("IfcWall", "W1"), ("IfcWallStandardCase", "W2"), ("IfcDoor", "P1")):
        _pset(f, _element(f, ifc_class, name), "Dados", _prop(f, "Marca", "IfcLabel", name))
    ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcSpace", name="Sala")

    info, rows = mp.map_file(_save(f, tmp_path, "m.ifc"), None)

    assert info["elementos_por_classe"] == {"IfcDoor": 1, "IfcWall": 1, "IfcWallStandardCase": 1}
    assert {(r["classe"], r["cobertura_pct"]) for r in rows} == {
        ("IfcDoor", 100.0),
        ("IfcWall", 100.0),
        ("IfcWallStandardCase", 100.0),
    }


def test_quantidades_usam_unidade_de_projeto_da_grandeza(tmp_path: Path) -> None:
    f = _new_file("IFC4", ("LENGTHUNIT", "VOLUMEUNIT"))
    slab = _element(f, "IfcSlab", "L1")
    qto = f.create_entity(
        "IfcElementQuantity",
        GlobalId=ifcopenshell.guid.new(),
        Name="Qto_SlabBaseQuantities",
        Quantities=[f.create_entity("IfcQuantityVolume", Name="NetVolume", VolumeValue=2.4)],
    )
    f.create_entity(
        "IfcRelDefinesByProperties",
        GlobalId=ifcopenshell.guid.new(),
        RelatedObjects=[slab],
        RelatingPropertyDefinition=qto,
    )

    _, rows = mp.map_file(_save(f, tmp_path, "m.ifc"), ["IfcSlab"])

    assert (rows[0]["tipo_valor"], rows[0]["unidade"], rows[0]["unidade_origem"]) == (
        "IfcQuantityVolume",
        "CUBIC_METRE",
        "projeto",
    )


def test_alias_legado_e_so_anotado(tmp_path: Path) -> None:
    f = _new_file("IFC4")
    _pset(f, _element(f, "IfcColumn", "C1"), "Dados", _prop(f, "Fck", "IfcReal", 30.0))

    _, rows = mp.map_file(_save(f, tmp_path, "m.ifc"), ["IfcColumn"])

    assert rows[0]["propriedade"] == "Fck"
    assert rows[0]["alias_legado_de"] == "CompressiveStrength"


def test_nome_canonico_da_tabela_legada_nao_vira_alias(tmp_path: Path) -> None:
    # A tabela legada lista LoadBearing como alias de IsLoadBearing e vice-versa;
    # LoadBearing é nome oficial em Pset_SlabCommon.
    f = _new_file("IFC4")
    _pset(
        f,
        _element(f, "IfcSlab", "L1"),
        "Pset_SlabCommon",
        _prop(f, "LoadBearing", "IfcBoolean", True),
    )

    _, rows = mp.map_file(_save(f, tmp_path, "m.ifc"), ["IfcSlab"])

    assert rows[0]["alias_legado_de"] == ""


@pytest.mark.parametrize(
    ("campo", "valor", "termo"),
    [
        ("propriedade", "Resistência característica", "resistencia"),
        ("pset", "Dados_Cobrimento", "cobrimento"),
        ("exemplos", "CAA III | CAA IV", "caa"),
    ],
)
def test_candidatos_de_termos_ignoram_acento_caixa_e_separador(
    campo: str, valor: str, termo: str
) -> None:
    row: dict[str, object] = {"propriedade": "X", "pset": "Y", "exemplos": ""}
    row[campo] = valor

    found = mp.term_candidates([row], [termo.upper()])

    assert [c["termo"] for c in found] == [termo]


def test_main_grava_as_quatro_saidas(tmp_path: Path) -> None:
    f = _new_file("IFC4")
    _pset(f, _element(f, "IfcColumn", "C1"), "Dados", _prop(f, "fck", "IfcReal", 30.0))
    path = _save(f, tmp_path, "m.ifc")
    out = tmp_path / "out"

    mp.main([str(path), "--classes", "IfcColumn", "--termos", "fck", "--out", str(out)])

    assert sorted(p.name for p in out.iterdir()) == [
        "candidatos_termos.csv",
        "manifesto.json",
        "matriz_softwares.csv",
        "propriedades_longo.csv",
    ]
    manifesto = json.loads((out / "manifesto.json").read_text(encoding="utf-8"))
    assert manifesto[0]["arquivo"] == "m.ifc"
    assert len(manifesto[0]["sha256"]) == 64
    with (out / "candidatos_termos.csv").open(encoding="utf-8-sig") as handle:
        assert [r["propriedade"] for r in csv.DictReader(handle)] == ["fck"]
