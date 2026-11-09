"""Camada fiel do Apêndice A de Daiane (2025) a partir da matriz canônica do M3 (M1-02).

A transcrição já existe e foi conferida página a página pela pesquisa M3
(``docs/pesquisa/modulo-03-contexto/matriz-canonica.json``). Este importador a lê
sem copiá-la: cada registro vira uma ``SourceAssertion`` com os literais exatos da
fonte, e as projeções CSV de cobertura e divergências são geradas da mesma revisão,
com hash. Nada é corrigido, normalizado ou deduplicado aqui. O Apêndice B, o XML
original e a planilha continuam pendentes e impedem declarar cobertura integral.
"""

import argparse
import csv
import hashlib
import io
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from loguru import logger
from pydantic import BaseModel, ConfigDict, ValidationError

from src.config import BASE_DIR
from src.domain_catalog.canonical import (
    CanonicalJSONError,
    canonical_json_bytes,
    canonical_json_text,
    parse_json_strict,
)
from src.domain_catalog.content import CatalogContent
from src.domain_catalog.drafts import load_draft
from src.domain_catalog.models import SourceArtifact, SourceAssertion

MATRIX_PATH = BASE_DIR / "docs" / "pesquisa" / "modulo-03-contexto" / "matriz-canonica.json"
E1_DRAFT_PATH = BASE_DIR / "data" / "catalogs" / "fixtures" / "daiane-e1-rascunho" / "rascunho.json"
"""Amostra da E1: dados reais da fonte e julgamentos semânticos em rascunho para revisão."""
MATRIX_SCHEMA_VERSION = "m3-planning-1.0"
DISSERTATION_ID = "dai2025:dissertacao"
IDS_XML_ID = "dai2025:ids-mestrado-xml"
SPREADSHEET_ID = "dai2025:planilha-requisitos"
REPORTED_DIVERGENCE_COUNT = 34
"""Contagem do levantamento anterior (consolidação de 09/10); inventário individual ausente."""

FAMILIES: tuple[str, ...] = tuple(f"A{n}" for n in range(1, 11))
ALPHANUMERIC_CATEGORIES: frozenset[str] = frozenset(
    {
        "entity",
        "attribute",
        "material",
        "classification",
        "custom_property",
        "standard_property",
        "quantity",
    }
)
_AUXILIARY_CATEGORIES: frozenset[str] = frozenset(
    {"metadata", "geometry_requirement", "document_requirement"}
)
_DECLARED_COUNT_KEYS: dict[str, frozenset[str] | None] = {
    "all_planning_records": None,
    "alphanumeric_records": ALPHANUMERIC_CATEGORIES,
    "metadata_records": frozenset({"metadata"}),
    "geometry_records": frozenset({"geometry_requirement"}),
    "document_records": frozenset({"document_requirement"}),
    "custom_property_entries": frozenset({"custom_property"}),
    "standard_property_entries": frozenset({"standard_property"}),
    "quantity_entries": frozenset({"quantity"}),
    "classification_groups": frozenset({"classification"}),
}
_LIFECYCLE_PT: dict[str, str] = {
    "draft": "rascunho",
    "reviewed": "revisado",
    "approved": "aprovado",
    "deprecated": "depreciado",
}
COVERAGE_FILE = "cobertura-daiane.csv"
DIVERGENCE_FILE = "divergencias-daiane.csv"
PROJECTION_MANIFEST_FILE = "projecoes-daiane.json"


class MatrixFormatError(ValueError):
    """Matriz ilegível, de versão desconhecida ou com registro inconsistente."""


class MatrixSnapshot(BaseModel):
    """Conteúdo bruto da matriz canônica com a identidade dos bytes lidos."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path_label: str
    sha256: str
    size_bytes: int
    schema_version: str
    revision: str
    provenance: dict[str, Any]
    declared_counts: dict[str, Any]
    declared_family_rows: dict[str, int]
    records: tuple[dict[str, Any], ...]


class ImportReport(BaseModel):
    """Denominadores, conferências e pendências da importação; não é certificado de cobertura."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    matrix_revision: str
    matrix_sha256: str
    matrix_schema_version: str
    counts_by_category: dict[str, int]
    alphanumeric_by_family: dict[str, int]
    families: tuple[str, ...]
    declared_count_mismatches: tuple[str, ...]
    appendix_b_status: Literal["pending_transcription"]
    pending_sources: tuple[str, ...]
    source_coverage_complete: bool
    reported_divergence_count: int
    matrix_divergence_records: int
    matrix_divergence_items: int


class DaianeImport(BaseModel):
    """Artefatos de fonte, assertivas fiéis e relatório de uma importação."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    artifacts: tuple[SourceArtifact, ...]
    assertions: tuple[SourceAssertion, ...]
    divergence_counts: dict[str, int]
    report: ImportReport


def _path_label(path: Path) -> str:
    """Caminho relativo ao repositório quando possível; nunca caminho absoluto local."""
    try:
        return path.resolve().relative_to(BASE_DIR.resolve()).as_posix()
    except ValueError:
        return path.name


def load_matrix(path: Path) -> MatrixSnapshot:
    """Lê a matriz com JSON estrito e registra hash e revisão do conteúdo lido.

    A identidade é o SHA-256 do texto UTF-8 normalizado para LF, mesma regra do
    builder de release (``scripts/build_windows_release.py``): o checkout no Windows
    pode gravar CRLF, e o hash não pode depender disso. Para arquivo já em LF, é o
    hash dos próprios bytes, igual ao do conteúdo versionado no Git.
    """
    try:
        text = path.read_bytes().decode("utf-8")
        raw = parse_json_strict(text)
    except (UnicodeDecodeError, CanonicalJSONError) as exc:
        raise MatrixFormatError(f"matriz ilegível em {path.name}: {exc}") from exc
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    if not isinstance(raw, dict):
        raise MatrixFormatError("matriz precisa ser um objeto JSON")
    if raw.get("schema_version") != MATRIX_SCHEMA_VERSION:
        raise MatrixFormatError(
            f"schema_version {raw.get('schema_version')!r} não suportado; "
            f"esperado {MATRIX_SCHEMA_VERSION}"
        )
    revision = raw.get("revision")
    records = raw.get("records")
    if not isinstance(revision, str) or not revision:
        raise MatrixFormatError("matriz sem revision")
    if not isinstance(records, list) or not all(isinstance(r, dict) for r in records):
        raise MatrixFormatError("matriz sem lista de records")
    coverage = (raw.get("source_matrix_original") or {}).get("coverage") or {}
    family_rows = {
        str(item["family_id"]): int(item["alphanumeric_rows"])
        for item in coverage.get("by_family") or []
    }
    return MatrixSnapshot(
        path_label=_path_label(path),
        sha256=hashlib.sha256(normalized).hexdigest(),
        size_bytes=len(normalized),
        schema_version=MATRIX_SCHEMA_VERSION,
        revision=revision,
        provenance=dict(raw.get("provenance") or {}),
        declared_counts=dict(raw.get("counts") or {}),
        declared_family_rows=family_rows,
        records=tuple(records),
    )


def _artifacts(snapshot: MatrixSnapshot) -> tuple[SourceArtifact, ...]:
    """Dissertação, matriz de transcrição e fontes originais ainda não obtidas."""
    provenance = snapshot.provenance
    return (
        SourceArtifact(
            id=DISSERTATION_ID,
            title=(
                "Gestão da informação em modelos BIM para orçamentação de obras públicas "
                "com uso do Information Delivery Specification"
            ),
            authors=("Daiane Castro Dias",),
            issued="2025",
            artifact_type="dissertation",
            location=provenance.get("source_url"),
            sha256=provenance.get("pdf_sha256"),
            terms="Dissertação IME; PDF não redistribuído pelo repositório",
            notes=(
                "Apêndice A: pp. impressas 161–170 (PDF 162–171); Apêndice B, relatório "
                "IDS_Mestrado: pp. 171–185 (PDF 172–186); Apêndice C a partir da p. 187 "
                "(PDF 188). Paginação conferida no PDF local em 13/10/2026."
            ),
        ),
        SourceArtifact(
            id=f"m3:matriz-canonica-{snapshot.revision}",
            title="Matriz canônica do Apêndice A (apoio do M3)",
            authors=("pesquisa M3 do IFC Quality Copilot",),
            issued=snapshot.revision,
            artifact_type="research_matrix",
            location=snapshot.path_label,
            sha256=snapshot.sha256,
            size_bytes=snapshot.size_bytes,
            terms="Artefato interno do projeto",
            notes=(
                "Transcrição do PDF com páginas conferidas visualmente pela pesquisa M3; "
                "conferência pelo curador pendente."
            ),
        ),
        SourceArtifact(
            id=IDS_XML_ID,
            title="IDS_Mestrado — XML original (10 especificações, versão 1, 22/08/2025)",
            authors=("Daiane Castro Dias",),
            issued="2025-08-22",
            artifact_type="ids_xml",
            terms="Desconhecidos; arquivo não obtido",
            notes=(
                "Arquivo não obtido. O relatório do Apêndice B é a única representação "
                "disponível; busca com Juliana encaminhada (D10). O IDS_Cost de 2026 é outra "
                "fonte e não o substitui."
            ),
        ),
        SourceArtifact(
            id=SPREADSHEET_ID,
            title="Planilha editável de requisitos da dissertação",
            authors=("Daiane Castro Dias",),
            issued="2025",
            artifact_type="spreadsheet",
            terms="Desconhecidos; arquivo não obtido",
            notes="Arquivo não obtido; busca com Juliana encaminhada (D10).",
        ),
    )


def _assertion(record: dict[str, Any], transcription_id: str) -> SourceAssertion:
    """Converte um registro em assertiva, sem alterar nenhum literal."""
    record_id = record.get("record_id")
    layer = record.get("source_layer")
    if not isinstance(layer, dict):
        raise MatrixFormatError(f"{record_id}: source_layer ausente")
    family = str(record.get("family_id", ""))
    if not str(record_id).startswith(f"{family}-") or family not in FAMILIES:
        raise MatrixFormatError(f"{record_id}: family_id {family!r} incoerente")
    domain = layer.get("domain_literal")
    try:
        return SourceAssertion.model_validate(
            {
                "id": f"dai2025:{record_id}",
                "source_artifact_id": DISSERTATION_ID,
                "transcription_artifact_id": transcription_id,
                "locator": {
                    "printed_page": record.get("printed_page"),
                    "pdf_page": record.get("pdf_page"),
                    "table": f"Quadro A.{family[1:]}",
                    "row_ref": record_id,
                },
                "category": record.get("category"),
                "target_literal": layer.get("target_literal"),
                "target_identifier_literal": layer.get("target_identifier_literal"),
                "set_literal": layer.get("pset_literal"),
                "datatype_literal": layer.get("datatype_literal"),
                "unit_literal": layer.get("unit_literal"),
                "domain_literal_json": None if domain is None else canonical_json_text(domain),
                "notes": tuple(record.get("source_notes") or ()),
                "transcription_status": "checked_by_research",
            }
        )
    except ValidationError as exc:
        raise MatrixFormatError(f"{record_id}: registro inconsistente: {exc}") from exc


def _discrepancies(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Itens de divergência registrados pela pesquisa para o registro."""
    operational = record.get("operational_layer") or {}
    return list(operational.get("source_discrepancies") or [])


def import_appendix_a(snapshot: MatrixSnapshot) -> DaianeImport:
    """Importa todos os registros da matriz e compara as contagens declaradas."""
    artifacts = _artifacts(snapshot)
    transcription_id = artifacts[1].id
    seen: set[str] = set()
    assertions: list[SourceAssertion] = []
    divergence_counts: dict[str, int] = {}
    for record in snapshot.records:
        record_id = str(record.get("record_id"))
        if record_id in seen:
            raise MatrixFormatError(f"record_id duplicado na matriz: {record_id}")
        seen.add(record_id)
        assertion = _assertion(record, transcription_id)
        assertions.append(assertion)
        divergence_counts[assertion.id] = len(_discrepancies(record))

    by_category: Counter[str] = Counter(str(a.category) for a in assertions)
    by_family = Counter(
        str(a.locator.row_ref).split("-")[0]
        for a in assertions
        if a.category in ALPHANUMERIC_CATEGORIES
    )
    mismatches: list[str] = []
    for key, categories in _DECLARED_COUNT_KEYS.items():
        if key not in snapshot.declared_counts:
            continue
        computed = (
            len(assertions)
            if categories is None
            else sum(by_category[category] for category in categories)
        )
        if computed != snapshot.declared_counts[key]:
            mismatches.append(f"{key}: declarado {snapshot.declared_counts[key]}, lido {computed}")
    for family, declared in snapshot.declared_family_rows.items():
        if by_family.get(family, 0) != declared:
            mismatches.append(f"{family}: declarado {declared}, lido {by_family.get(family, 0)}")

    pending = ("apendice_b", "ids_xml_2025", "planilha_editavel", "inventario_34_divergencias")
    report = ImportReport(
        matrix_revision=snapshot.revision,
        matrix_sha256=snapshot.sha256,
        matrix_schema_version=snapshot.schema_version,
        counts_by_category=dict(sorted(by_category.items())),
        alphanumeric_by_family={
            family: by_family[family] for family in FAMILIES if by_family[family]
        },
        families=tuple(family for family in FAMILIES if by_family[family]),
        declared_count_mismatches=tuple(mismatches),
        appendix_b_status="pending_transcription",
        pending_sources=pending,
        source_coverage_complete=not pending,
        reported_divergence_count=REPORTED_DIVERGENCE_COUNT,
        matrix_divergence_records=sum(1 for count in divergence_counts.values() if count),
        matrix_divergence_items=sum(divergence_counts.values()),
    )
    if mismatches:
        logger.warning("Contagens divergentes da matriz {}: {}", snapshot.revision, mismatches)
    return DaianeImport(
        artifacts=artifacts,
        assertions=tuple(assertions),
        divergence_counts=divergence_counts,
        report=report,
    )


def coverage_rows(
    imported: DaianeImport, content: CatalogContent | None = None
) -> list[dict[str, str]]:
    """Uma linha por assertiva, com eixos de cobertura separados (plano M1 §5.3)."""
    bindings_by_assertion: dict[str, list[tuple[str, str]]] = {}
    for binding in content.bindings if content is not None else ():
        for assertion_id in binding.source_assertion_ids:
            bindings_by_assertion.setdefault(assertion_id, []).append(
                (binding.id, binding.lifecycle)
            )
    rows: list[dict[str, str]] = []
    for assertion in imported.assertions:
        linked = bindings_by_assertion.get(assertion.id, [])
        states = sorted({_LIFECYCLE_PT[lifecycle] for _, lifecycle in linked})
        auxiliary = assertion.category in _AUXILIARY_CATEGORIES
        rows.append(
            {
                "canonical_revision": imported.report.matrix_revision,
                "source_entry_id": assertion.id,
                "family_id": str(assertion.locator.row_ref).split("-")[0],
                "table": assertion.locator.table or "",
                "printed_page": str(assertion.locator.printed_page or ""),
                "pdf_page": str(assertion.locator.pdf_page or ""),
                "category": assertion.category,
                "set_literal": assertion.set_literal or "",
                "target_identifier_literal": assertion.target_identifier_literal or "",
                "target_literal": assertion.target_literal,
                "datatype_literal": assertion.datatype_literal or "",
                "unit_literal": assertion.unit_literal or "",
                "domain_literal_json": assertion.domain_literal_json or "",
                "transcription_status": assertion.transcription_status,
                "appendix_b_status": "pendente_transcricao",
                "catalog_status": "|".join(states) or "nao_cadastrado",
                "catalog_binding_ids": "|".join(sorted(bid for bid, _ in linked)),
                "validation_support": "nao_avaliado",
                "enrichment_support": "nao_operacionalizado" if auxiliary else "indisponivel",
                "divergence_items": str(imported.divergence_counts.get(assertion.id, 0)),
            }
        )
    return rows


def divergence_rows(snapshot: MatrixSnapshot) -> list[dict[str, str]]:
    """Um item de divergência por linha, preservado integralmente em ``item_json``."""
    rows: list[dict[str, str]] = []
    for record in snapshot.records:
        source_entry_id = f"dai2025:{record.get('record_id')}"
        layer = record.get("source_layer") or {}
        for index, item in enumerate(_discrepancies(record), start=1):
            text = item.get("issue") or item.get("detail") or item.get("description") or ""
            rows.append(
                {
                    "canonical_revision": snapshot.revision,
                    "divergence_row_id": f"{source_entry_id}#{index}",
                    "source_entry_id": source_entry_id,
                    "family_id": str(record.get("family_id", "")),
                    "category": str(record.get("category", "")),
                    "target_identifier_literal": str(layer.get("target_identifier_literal") or ""),
                    "item_source": str(item.get("source") or ""),
                    "item_text": str(text),
                    "item_json": canonical_json_text(item),
                    "status": "aberta",
                }
            )
    return rows


def _csv_bytes(rows: Sequence[dict[str, str]]) -> bytes:
    """CSV UTF-8 sem BOM, separador vírgula e LF, como as projeções do M3."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def load_daiane_draft(path: Path, imported: DaianeImport) -> CatalogContent:
    """Rascunho de curadoria apoiado nesta importação; recusa base de outra revisão."""
    return load_draft(
        path,
        source_artifacts=imported.artifacts,
        source_assertions=imported.assertions,
        expected_base={
            "matrix_revision": imported.report.matrix_revision,
            "matrix_sha256": imported.report.matrix_sha256,
        },
    )


def write_projections(
    matrix_path: Path, out_dir: Path, draft_path: Path | None = None
) -> dict[str, Any]:
    """Gera cobertura, divergências e o manifesto das projeções a partir da mesma revisão."""
    snapshot = load_matrix(matrix_path)
    imported = import_appendix_a(snapshot)
    content = None if draft_path is None else load_daiane_draft(draft_path, imported)
    tables = {
        COVERAGE_FILE: coverage_rows(imported, content),
        DIVERGENCE_FILE: divergence_rows(snapshot),
    }
    outputs = {name: _csv_bytes(rows) for name, rows in tables.items()}
    manifest: dict[str, Any] = {
        "generator": "src.domain_catalog.importers.daiane",
        "matrix": {
            "path": snapshot.path_label,
            "revision": snapshot.revision,
            "sha256": snapshot.sha256,
        },
        "catalog_draft": (
            None
            if draft_path is None or content is None
            else {
                "path": _path_label(draft_path),
                "file_sha256": hashlib.sha256(draft_path.read_bytes()).hexdigest(),
                "content_sha256": hashlib.sha256(
                    canonical_json_bytes(content.model_dump(mode="json"))
                ).hexdigest(),
            }
        ),
        "outputs": {
            name: {"sha256": hashlib.sha256(data).hexdigest(), "rows": len(tables[name])}
            for name, data in outputs.items()
        },
        "report": imported.report.model_dump(mode="json"),
        "note": (
            "Projeções derivadas; não editar à mão. Regenerar com "
            "python -m src.domain_catalog.importers.daiane."
        ),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, data in outputs.items():
        (out_dir / name).write_bytes(data)
    (out_dir / PROJECTION_MANIFEST_FILE).write_bytes(canonical_json_bytes(manifest))
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    """Regenera as projeções de cobertura e divergências do Apêndice A."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=MATRIX_PATH)
    parser.add_argument("--out", type=Path, default=BASE_DIR / "docs" / "catalogo")
    parser.add_argument("--draft", type=Path, default=E1_DRAFT_PATH)
    args = parser.parse_args(argv)
    manifest = write_projections(args.matrix, args.out, args.draft)
    logger.info("Projeções geradas em {}: {}", args.out, manifest["outputs"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
