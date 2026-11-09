"""Camada fiel do Apêndice A importada da matriz canônica M3 (M1-02).

Usa a matriz REAL versionada (revisão ``2026-10-12-r2``). As contagens esperadas
vêm da tabela de denominadores de ``docs/pesquisa/modulo-03-contexto/README.md`` e
de contagem independente (147 itens de divergência em 112 registros), não do código
testado. Os testes negativos usam matrizes SINTÉTICAS mínimas em ``tmp_path``.
"""

import json
import re
from pathlib import Path

import pytest

from src.config import BASE_DIR
from src.domain_catalog.content import CatalogContent, validate_content
from src.domain_catalog.importers.daiane import (
    E1_DRAFT_PATH,
    DaianeImport,
    MatrixFormatError,
    coverage_rows,
    import_appendix_a,
    load_matrix,
    write_projections,
)
from src.domain_catalog.models import SourceAssertion

MATRIX = BASE_DIR / "docs" / "pesquisa" / "modulo-03-contexto" / "matriz-canonica.json"
CATALOG_DOCS = BASE_DIR / "docs" / "catalogo"


@pytest.fixture(scope="module")
def imported() -> DaianeImport:
    return import_appendix_a(load_matrix(MATRIX))


@pytest.fixture(scope="module")
def by_id(imported: DaianeImport) -> dict[str, SourceAssertion]:
    return {assertion.id: assertion for assertion in imported.assertions}


@pytest.mark.external_data
def test_matrix_identity_is_the_versioned_lf_content(imported: DaianeImport) -> None:
    # SHA-256 do blob versionado (git show HEAD:...), igual ao conteúdo normalizado para LF.
    assert imported.report.matrix_revision == "2026-10-12-r2"
    assert imported.report.matrix_sha256 == (
        "771f12f2dda08f18d6e58ba886b956ef31fc561ea40f9a5a58b649dfa92ce2ce"
    )


@pytest.mark.external_data
def test_matrix_identity_does_not_depend_on_checkout_line_endings(tmp_path: Path) -> None:
    lf = MATRIX.read_bytes().replace(b"\r\n", b"\n")
    (tmp_path / "lf.json").write_bytes(lf)
    (tmp_path / "crlf.json").write_bytes(lf.replace(b"\n", b"\r\n"))

    from_lf = load_matrix(tmp_path / "lf.json")
    from_crlf = load_matrix(tmp_path / "crlf.json")

    assert (from_lf.sha256, from_lf.size_bytes) == (from_crlf.sha256, from_crlf.size_bytes)
    assert re.fullmatch(r"[0-9a-f]{64}", from_lf.sha256)


@pytest.mark.external_data
def test_every_record_becomes_one_assertion_with_stable_id(imported: DaianeImport) -> None:
    ids = [assertion.id for assertion in imported.assertions]

    assert len(ids) == len(set(ids)) == 313
    assert {"dai2025:A7-010", "dai2025:A1-G01", "dai2025:A10-009", "dai2025:A7-D01"} <= set(ids)


@pytest.mark.external_data
def test_denominators_match_the_audited_m3_table(imported: DaianeImport) -> None:
    report = imported.report

    assert report.counts_by_category == {
        "entity": 10,
        "attribute": 28,
        "material": 10,
        "classification": 19,
        "custom_property": 82,
        "standard_property": 36,
        "quantity": 18,
        "metadata": 50,
        "geometry_requirement": 50,
        "document_requirement": 10,
    }
    assert report.alphanumeric_by_family == {
        "A1": 24, "A2": 28, "A3": 26, "A4": 22, "A5": 19,
        "A6": 24, "A7": 18, "A8": 16, "A9": 17, "A10": 9,
    }  # fmt: skip
    assert report.declared_count_mismatches == ()


@pytest.mark.external_data
def test_cost_prop_never_replaces_eb_orcamento(imported: DaianeImport) -> None:
    texts = [
        (assertion.set_literal or "") + (assertion.target_literal or "")
        for assertion in imported.assertions
    ]

    assert not any("Cost_Prop" in text for text in texts)
    assert sum(a.set_literal == "EB_Orçamento" for a in imported.assertions) == 82


@pytest.mark.external_data
def test_locator_separates_printed_and_pdf_pages(by_id: dict[str, SourceAssertion]) -> None:
    locator = by_id["dai2025:A7-010"].locator

    assert (locator.printed_page, locator.pdf_page, locator.table, locator.row_ref) == (
        167,
        168,
        "Quadro A.7",
        "A7-010",
    )


@pytest.mark.external_data
def test_assertions_cite_dissertation_and_transcription(imported: DaianeImport) -> None:
    artifacts = {artifact.id: artifact for artifact in imported.artifacts}

    assert {a.source_artifact_id for a in imported.assertions} == {"dai2025:dissertacao"}
    assert {a.transcription_artifact_id for a in imported.assertions} == {
        "m3:matriz-canonica-2026-10-12-r2"
    }
    assert artifacts["dai2025:dissertacao"].sha256 == (
        "82ead7b5f06fd06247f9f057727bab071ab1c08de4fe42412bebeb9e0c06877a"
    )
    assert artifacts["m3:matriz-canonica-2026-10-12-r2"].sha256 == imported.report.matrix_sha256
    assert {a.transcription_status for a in imported.assertions} == {"checked_by_research"}


@pytest.mark.external_data
def test_absent_original_sources_are_registered_without_hash(imported: DaianeImport) -> None:
    artifacts = {artifact.id: artifact for artifact in imported.artifacts}

    for absent in ("dai2025:ids-mestrado-xml", "dai2025:planilha-requisitos"):
        assert artifacts[absent].sha256 is None
        assert "não obtido" in (artifacts[absent].notes or "")


@pytest.mark.external_data
def test_imported_sources_form_valid_content(imported: DaianeImport) -> None:
    content = CatalogContent(
        source_artifacts=imported.artifacts, source_assertions=imported.assertions
    )

    validate_content(content, for_release=False)


@pytest.mark.external_data
def test_source_coverage_is_never_complete_while_appendix_b_is_pending(
    imported: DaianeImport,
) -> None:
    report = imported.report

    assert report.appendix_b_status == "pending_transcription"
    assert report.source_coverage_complete is False
    assert {"apendice_b", "ids_xml_2025", "planilha_editavel", "inventario_34_divergencias"} <= set(
        report.pending_sources
    )


@pytest.mark.external_data
def test_reported_divergence_count_stays_apart_from_matrix_findings(imported: DaianeImport) -> None:
    report = imported.report

    assert (
        report.reported_divergence_count,
        report.matrix_divergence_records,
        report.matrix_divergence_items,
    ) == (34, 112, 147)


@pytest.mark.external_data
def test_coverage_projection_has_one_row_per_assertion_with_separate_axes(
    imported: DaianeImport,
) -> None:
    rows = coverage_rows(imported)
    row = next(row for row in rows if row["source_entry_id"] == "dai2025:A7-010")

    assert len(rows) == 313
    assert row["catalog_status"] == "nao_cadastrado"
    assert row["appendix_b_status"] == "pendente_transcricao"
    assert row["validation_support"] == "nao_avaliado"
    assert row["enrichment_support"] == "indisponivel"


@pytest.mark.external_data
def test_committed_projections_match_regeneration(tmp_path: Path) -> None:
    # O gerador grava LF; um checkout com autocrlf pode trazer os CSV em CRLF.
    write_projections(MATRIX, tmp_path, E1_DRAFT_PATH)

    for name in ("cobertura-daiane.csv", "divergencias-daiane.csv", "projecoes-daiane.json"):
        committed = (CATALOG_DOCS / name).read_bytes().replace(b"\r\n", b"\n")
        assert (tmp_path / name).read_bytes() == committed, name


# --- Matrizes sintéticas para falhas de formato ----------------------------------------


def _synthetic_matrix(tmp_path: Path, **changes: object) -> Path:
    record = {
        "record_id": "A1-001",
        "family_id": "A1",
        "category": "entity",
        "printed_page": 161,
        "pdf_page": 162,
        "source_layer": {
            "target_literal": "Classe IFC",
            "target_identifier_literal": "Classe IFC",
            "pset_literal": None,
            "datatype_literal": None,
            "unit_literal": None,
            "domain_literal": ["IfcWindow"],
        },
        "source_notes": [],
        "operational_layer": {"source_discrepancies": []},
    }
    data: dict[str, object] = {
        "schema_version": "m3-planning-1.0",
        "revision": "sintetica-1",
        "records": [record],
    }
    data.update(changes)
    path = tmp_path / "matriz-sintetica.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_unknown_matrix_schema_is_refused(tmp_path: Path) -> None:
    with pytest.raises(MatrixFormatError, match="schema_version"):
        load_matrix(_synthetic_matrix(tmp_path, schema_version="m3-planning-2.0"))


def test_duplicate_record_ids_are_refused(tmp_path: Path) -> None:
    path = _synthetic_matrix(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["records"].append(data["records"][0])
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(MatrixFormatError, match="duplicad"):
        import_appendix_a(load_matrix(path))


def test_duplicate_json_keys_in_matrix_are_refused(tmp_path: Path) -> None:
    path = tmp_path / "chave-duplicada.json"
    path.write_text(
        '{"schema_version": "m3-planning-1.0", "revision": "a", "revision": "b", "records": []}',
        encoding="utf-8",
    )

    with pytest.raises(MatrixFormatError, match="duplicada"):
        load_matrix(path)


def test_record_without_target_literal_is_refused(tmp_path: Path) -> None:
    path = _synthetic_matrix(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["records"][0]["source_layer"]["target_literal"] = ""
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(MatrixFormatError, match="A1-001"):
        import_appendix_a(load_matrix(path))


def test_declared_counts_that_disagree_are_reported_not_forced(tmp_path: Path) -> None:
    path = _synthetic_matrix(
        tmp_path, counts={"all_planning_records": 2, "alphanumeric_records": 1}
    )

    report = import_appendix_a(load_matrix(path)).report

    assert report.declared_count_mismatches == ("all_planning_records: declarado 2, lido 1",)


def test_record_family_must_match_its_id(tmp_path: Path) -> None:
    path = _synthetic_matrix(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["records"][0]["family_id"] = "A2"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(MatrixFormatError, match="family_id"):
        import_appendix_a(load_matrix(path))
