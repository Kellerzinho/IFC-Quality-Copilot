"""Exportador BCFXML 3.0 para issues."""

from __future__ import annotations

from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5
from zipfile import ZIP_DEFLATED, ZipFile

from lxml import etree

from src.models import Issue

BCF_NAMESPACE = "http://schemas.opengis.net/bcf/3.0"


class BCFExporter:
    """Exporta issues como BCFXML 3.0."""

    def export(self, issues: list[Issue], output_path: Path) -> Path:
        """Gera arquivo .bcf com um topic por issue.

        Para cada issue:
        - Topic GUID: usar issue.id (ou gerar UUID se necessário)
        - Title: issue.description
        - Priority: mapear issue.severity para o vocabulário do BCF
        - Status: mapear issue.status para o vocabulário do BCF
        - Description: incluir dados essenciais do elemento IFC
        - ReferenceLink: incluir o GUID IFC do componente relacionado

        Retorna o caminho do arquivo gerado.
        """
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        with ZipFile(target, "w", compression=ZIP_DEFLATED) as bcf_zip:
            bcf_zip.writestr("bcf.version", self._create_version_xml())

            for issue in issues:
                topic_guid = self._topic_guid(issue)
                bcf_zip.writestr(f"{topic_guid}/markup.bcf", self._create_markup_xml(issue))

        return target

    def _create_version_xml(self) -> str:
        """Retorna XML de bcf.version para BCF 3.0."""
        root = etree.Element("Version", VersionId="3.0")
        return self._serialize_xml(root)

    def _create_markup_xml(self, issue: Issue) -> str:
        """Retorna XML de markup.bcf para um topic."""
        nsmap = {None: BCF_NAMESPACE}
        markup = etree.Element("Markup", nsmap=nsmap)
        header = etree.SubElement(markup, "Header")
        files = etree.SubElement(header, "Files")
        etree.SubElement(files, "File", IfcProject=issue.element_guid, IsExternal="false")

        topic = etree.SubElement(
            markup,
            "Topic",
            Guid=self._topic_guid(issue),
            TopicType=issue.issue_type,
            TopicStatus=self._map_status(issue.status),
        )
        etree.SubElement(topic, "Title").text = issue.description
        etree.SubElement(topic, "Priority").text = self._map_priority(issue.severity)
        etree.SubElement(topic, "CreationDate").text = issue.created_at.isoformat()
        etree.SubElement(topic, "Description").text = self._build_description(issue)
        etree.SubElement(topic, "ReferenceLink").text = issue.element_guid

        labels = etree.SubElement(topic, "Labels")
        etree.SubElement(labels, "Label").text = issue.element_class
        etree.SubElement(labels, "Label").text = issue.issue_type

        return self._serialize_xml(markup)

    def _map_priority(self, severity: str) -> str:
        """Mapeia severidade interna para prioridade BCF."""
        return {
            "high": "Critical",
            "medium": "Major",
            "low": "Normal",
        }[severity]

    def _map_status(self, status: str) -> str:
        """Mapeia status interno para status BCF."""
        if status == "pending":
            return "Open"
        return "Closed"

    def _build_description(self, issue: Issue) -> str:
        """Monta a descrição textual do tópico BCF."""
        return "\n".join(
            [
                f"element_class: {issue.element_class}",
                f"element_guid: {issue.element_guid}",
                f"issue_type: {issue.issue_type}",
            ]
        )

    def _topic_guid(self, issue: Issue) -> str:
        """Retorna GUID válido para o tópico BCF."""
        try:
            return str(UUID(str(issue.id)))
        except (ValueError, TypeError, AttributeError):
            if issue.id:
                return str(uuid5(NAMESPACE_URL, str(issue.id)))
            return str(uuid4())

    def _serialize_xml(self, root: etree._Element) -> str:
        """Serializa um elemento XML como texto UTF-8 com declaração."""
        return etree.tostring(root, encoding="utf-8", xml_declaration=True, pretty_print=True).decode(
            "utf-8"
        )
