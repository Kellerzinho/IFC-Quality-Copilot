"""Testes para src/translator/ids_parser.py."""

from pathlib import Path

from src.models import IDSSpecification
from src.translator.ids_parser import parse_ids

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
