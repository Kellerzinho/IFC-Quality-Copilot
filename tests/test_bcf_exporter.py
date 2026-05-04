"""Testes para exportação BCFXML 3.0."""

from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile, is_zipfile

from lxml import etree

from src.bcf import BCFExporter
from src.models import Issue

VALID_GUID = "3nJOFsJsX8QO2odKZbQnBj"
BCF_NS = {"bcf": "http://schemas.opengis.net/bcf/3.0"}


def _make_issue(**kwargs) -> Issue:
    """Cria issue padrão para os testes de exportação."""
    defaults = dict(
        id="issue-001",
        element_guid=VALID_GUID,
        element_class="IfcWall",
        issue_type="pset_missing",
        severity="medium",
        description="Pset obrigatório ausente.",
        status="pending",
    )
    defaults.update(kwargs)
    return Issue(**defaults)


def _read_xml_from_zip(bcf_path: Path, member_name: str) -> etree._Element:
    """Lê e parseia XML do arquivo BCF zipado."""
    with ZipFile(bcf_path, "r") as archive:
        content = archive.read(member_name)
    return etree.fromstring(content)


def test_export_creates_valid_bcf_file(tmp_path: Path) -> None:
    """Deve gerar um .bcf zipado com versionamento e topics."""
    exporter = BCFExporter()
    issues = [
        _make_issue(id="issue-001"),
        _make_issue(id="issue-002", description="Segunda issue."),
    ]
    output_path = tmp_path / "issues.bcf"

    result = exporter.export(issues, output_path)

    assert result == output_path
    assert result.exists()
    assert is_zipfile(result) is True

    with ZipFile(result, "r") as archive:
        names = archive.namelist()

    assert "bcf.version" in names
    topic_markups = [name for name in names if name.endswith("markup.bcf")]
    assert len(topic_markups) == 2


def test_export_maps_severity_to_priority(tmp_path: Path) -> None:
    """Deve mapear severidade interna para prioridade BCF."""
    exporter = BCFExporter()
    issue = _make_issue(id="issue-high", severity="high")
    output_path = tmp_path / "priority.bcf"

    exporter.export([issue], output_path)

    with ZipFile(output_path, "r") as archive:
        markup_name = next(name for name in archive.namelist() if name.endswith("markup.bcf"))

    root = _read_xml_from_zip(output_path, markup_name)
    priority = root.findtext(".//bcf:Priority", namespaces=BCF_NS)

    assert priority == "Critical"


def test_export_maps_status(tmp_path: Path) -> None:
    """Deve mapear status interno para status BCF."""
    exporter = BCFExporter()
    issue = _make_issue(id="issue-accepted", status="accepted")
    output_path = tmp_path / "status.bcf"

    exporter.export([issue], output_path)

    with ZipFile(output_path, "r") as archive:
        markup_name = next(name for name in archive.namelist() if name.endswith("markup.bcf"))

    root = _read_xml_from_zip(output_path, markup_name)
    topic = root.find(".//bcf:Topic", namespaces=BCF_NS)

    assert topic is not None
    assert topic.attrib["TopicStatus"] == "Closed"


def test_export_empty_list_creates_valid_bcf(tmp_path: Path) -> None:
    """Deve criar .bcf válido mesmo sem topics."""
    exporter = BCFExporter()
    output_path = tmp_path / "empty.bcf"

    exporter.export([], output_path)

    assert output_path.exists()
    assert is_zipfile(output_path) is True

    with ZipFile(output_path, "r") as archive:
        names = archive.namelist()

    assert names == ["bcf.version"]


def test_markup_contains_element_guid(tmp_path: Path) -> None:
    """markup.bcf deve incluir o GUID IFC do elemento."""
    exporter = BCFExporter()
    issue = _make_issue(id="issue-guid", element_guid=VALID_GUID)
    output_path = tmp_path / "guid.bcf"

    exporter.export([issue], output_path)

    with ZipFile(output_path, "r") as archive:
        markup_name = next(name for name in archive.namelist() if name.endswith("markup.bcf"))

    root = _read_xml_from_zip(output_path, markup_name)
    description = root.findtext(".//bcf:Description", namespaces=BCF_NS)
    reference_link = root.findtext(".//bcf:ReferenceLink", namespaces=BCF_NS)
    file_node = root.find(".//bcf:File", namespaces=BCF_NS)

    assert description is not None
    assert VALID_GUID in description
    assert reference_link == VALID_GUID
    assert file_node is not None
    assert file_node.attrib["IfcProject"] == VALID_GUID
