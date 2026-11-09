"""Projeções E4 do perfil Daiane: determinismo, totais e recusa de sobrescrita (Task 3).

Gera em ``tmp_path`` a partir dos artefatos REAIS e confere que as projeções versionadas
em ``docs/catalogo/e4/`` são exatamente a regeneração, sem edição manual. Os nomes E1 do
diretório raiz ``docs/catalogo/`` não são tocados.
"""

import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any

import pytest

from src.config import BASE_DIR
from src.domain_catalog.canonical import canonical_json_bytes
from src.domain_catalog.importers.daiane import MATRIX_PATH, import_appendix_a, load_matrix
from src.domain_catalog.importers.daiane_b import APPENDIX_B_PATH, load_appendix_b
from src.domain_catalog.profile import (
    ARCHIVE_RECORD_FILE,
    CANDIDATES_PATH,
    CORRESPONDENCE_FIELDS,
    CORRESPONDENCE_FILE,
    COVERAGE_FIELDS,
    COVERAGE_FILE,
    DIVERGENCE_FIELDS,
    DIVERGENCE_FILE,
    MANIFEST_FILE,
    PDF_SHA256,
    RECONCILIATION_HASH_SCHEME,
    RECONCILIATION_PATH,
    REVISIONS_DIR,
    ProfileReconciliationError,
    a_literals,
    build_daiane_profile,
    load_candidates,
    load_reconciliation,
    main,
    reconciliation_sha256,
    summarize_daiane_profile,
    write_profile_projections,
)
from src.domain_catalog.profile_models import (
    DaianeProfileInventory,
    ProfileCapabilityEvidence,
    ProfileReconciliation,
)

E4_DOCS = BASE_DIR / "docs" / "catalogo" / "e4"
E1_PROJECTIONS = BASE_DIR / "docs" / "catalogo"


@pytest.fixture(scope="module")
def inputs() -> dict[str, Any]:
    appendix_a = import_appendix_a(load_matrix(MATRIX_PATH))
    appendix_b = load_appendix_b(APPENDIX_B_PATH, expected_pdf_sha256=PDF_SHA256)
    reconciliation = load_reconciliation(RECONCILIATION_PATH)
    profile = build_daiane_profile(
        appendix_a,
        appendix_b,
        reconciliation,
        load_candidates(CANDIDATES_PATH, appendix_a, appendix_b),
        capabilities=ProfileCapabilityEvidence(),
    )
    return {"a": appendix_a, "profile": profile, "report": summarize_daiane_profile(profile)}


def _write(inputs: dict[str, Any], out: Path, **kwargs: Any) -> Any:
    return write_profile_projections(
        inputs["profile"], inputs["report"], out, a_literals=a_literals(inputs["a"]), **kwargs
    )


@pytest.mark.external_data
def test_regeneration_is_byte_identical(tmp_path: Path, inputs: dict[str, Any]) -> None:
    _write(inputs, tmp_path / "one")
    _write(inputs, tmp_path / "two")

    for name in (COVERAGE_FILE, DIVERGENCE_FILE, CORRESPONDENCE_FILE, MANIFEST_FILE):
        assert (tmp_path / "one" / name).read_bytes() == (tmp_path / "two" / name).read_bytes()
        assert b"\r\n" not in (tmp_path / "one" / name).read_bytes()


@pytest.mark.external_data
def test_manifest_hashes_and_row_totals_close(tmp_path: Path, inputs: dict[str, Any]) -> None:
    manifest = _write(inputs, tmp_path)
    rows = list(csv.DictReader(io.StringIO((tmp_path / COVERAGE_FILE).read_text(encoding="utf-8"))))

    for name, meta in manifest.outputs.items():
        data = (tmp_path / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == meta["sha256"]
    assert manifest.outputs[COVERAGE_FILE]["rows"] == len(rows) == 589
    assert [r["source_record_id"] for r in rows] == sorted(r["source_record_id"] for r in rows)
    assert {r["source_kind"] for r in rows} == {"A", "B"}
    assert manifest.outputs[DIVERGENCE_FILE]["rows"] == len(
        inputs["profile"].reconciliation.divergences
    )


@pytest.mark.external_data
def test_unprojected_b_rows_are_present_with_reason(tmp_path: Path, inputs: dict[str, Any]) -> None:
    _write(inputs, tmp_path)
    rows = {
        r["source_record_id"]: r
        for r in csv.DictReader(io.StringIO((tmp_path / COVERAGE_FILE).read_text(encoding="utf-8")))
    }
    row = rows["dai2025:B-E07-0018"]

    assert row["category"] == ""
    assert row["destination"] == "pending"
    assert "Area_Forma" in row["literal"]
    assert row["reason"]
    assert (row["printed_page"], row["pdf_page"]) == ("183", "184")


@pytest.mark.external_data
def test_semantic_change_changes_identity_but_reserialization_does_not(
    inputs: dict[str, Any], tmp_path: Path
) -> None:
    profile: DaianeProfileInventory = inputs["profile"]
    original = profile.reconciliation
    reread = ProfileReconciliation.model_validate(
        json.loads(json.dumps(original.model_dump(mode="json"), indent=4))
    )
    data = original.model_dump(mode="json")
    data["dispositions"][0]["reason"] += " (alterado)"
    changed = ProfileReconciliation.model_validate(data)

    assert reconciliation_sha256(reread) == reconciliation_sha256(original)
    assert reconciliation_sha256(changed) != reconciliation_sha256(original)


def _permuted(original: ProfileReconciliation) -> ProfileReconciliation:
    """Mesmo mapa ID→conteúdo, coleções não ordenadas em outra ordem."""
    data = original.model_dump(mode="json")
    for key in (
        "dispositions",
        "correspondences",
        "divergences",
        "identities",
        "family_map",
        "decisions",
        "historical_counts",
        "pending_sources",
    ):
        data[key].reverse()
    for item in data["dispositions"]:
        item["candidate_ids"].reverse()
        item["decision_ids"].reverse()
    for item in data["correspondences"]:
        item["a_record_ids"].reverse()
        item["b_record_ids"].reverse()
        item["compared_fields"].reverse()
    for item in data["divergences"]:
        item["source_record_ids"].reverse()
    return ProfileReconciliation.model_validate(data)


@pytest.mark.external_data
def test_permuting_unordered_collections_keeps_the_identity(inputs: dict[str, Any]) -> None:
    original: ProfileReconciliation = inputs["profile"].reconciliation
    permuted = _permuted(original)

    assert permuted.model_dump(mode="json") != original.model_dump(mode="json")
    assert reconciliation_sha256(permuted) == reconciliation_sha256(original)


@pytest.mark.external_data
def test_permuted_reconciliation_builds_the_same_profile_and_projections(
    tmp_path: Path, inputs: dict[str, Any]
) -> None:
    permuted = _permuted(inputs["profile"].reconciliation)
    a = inputs["a"]
    b = load_appendix_b(APPENDIX_B_PATH, expected_pdf_sha256=PDF_SHA256)
    built = build_daiane_profile(
        a,
        b,
        permuted,
        load_candidates(CANDIDATES_PATH, a, b),
        capabilities=ProfileCapabilityEvidence(),
    )
    _write(inputs, tmp_path / "original")
    write_profile_projections(
        built, summarize_daiane_profile(built), tmp_path / "permuted", a_literals=a_literals(a)
    )

    assert built.reconciliation_sha256 == inputs["profile"].reconciliation_sha256
    for name in (COVERAGE_FILE, DIVERGENCE_FILE, CORRESPONDENCE_FILE, MANIFEST_FILE):
        assert (tmp_path / "original" / name).read_bytes() == (
            tmp_path / "permuted" / name
        ).read_bytes(), name


@pytest.mark.external_data
def test_real_change_inside_an_id_set_changes_the_identity(inputs: dict[str, Any]) -> None:
    original: ProfileReconciliation = inputs["profile"].reconciliation
    data = original.model_dump(mode="json")
    target = next(d for d in data["divergences"] if len(d["source_record_ids"]) > 1)
    target["source_record_ids"].pop()

    assert reconciliation_sha256(ProfileReconciliation.model_validate(data)) != (
        reconciliation_sha256(original)
    )


@pytest.mark.external_data
def test_manifest_declares_the_reconciliation_hash_scheme(
    tmp_path: Path, inputs: dict[str, Any]
) -> None:
    manifest = _write(inputs, tmp_path)

    assert manifest.reconciliation_hash_scheme == RECONCILIATION_HASH_SCHEME
    assert RECONCILIATION_HASH_SCHEME == "ifcqc-daiane-recon-hash-2"


@pytest.mark.external_data
def test_builder_accepted_empty_correspondences_project_header_only(
    tmp_path: Path, inputs: dict[str, Any]
) -> None:
    """M11: lista vazia aceita pelo builder gera CSV só com cabeçalho, sem IndexError."""
    a = inputs["a"]
    b = load_appendix_b(APPENDIX_B_PATH, expected_pdf_sha256=PDF_SHA256)
    data = inputs["profile"].reconciliation.model_dump(mode="json")
    data["correspondences"] = []
    for disposition in data["dispositions"]:
        disposition["correspondence_ids"] = []
    built = build_daiane_profile(
        a,
        b,
        ProfileReconciliation.model_validate(data),
        load_candidates(CANDIDATES_PATH, a, b),
        capabilities=ProfileCapabilityEvidence(),
    )
    manifest = write_profile_projections(
        built, summarize_daiane_profile(built), tmp_path, a_literals=a_literals(a)
    )

    lines = (tmp_path / CORRESPONDENCE_FILE).read_text(encoding="utf-8").splitlines()
    assert lines == [",".join(CORRESPONDENCE_FIELDS)]
    assert manifest.outputs[CORRESPONDENCE_FILE]["rows"] == 0


@pytest.mark.external_data
def test_explicit_headers_match_the_written_files(tmp_path: Path, inputs: dict[str, Any]) -> None:
    _write(inputs, tmp_path)

    for name, fields in (
        (COVERAGE_FILE, COVERAGE_FIELDS),
        (DIVERGENCE_FILE, DIVERGENCE_FIELDS),
        (CORRESPONDENCE_FILE, CORRESPONDENCE_FIELDS),
    ):
        header = (tmp_path / name).read_text(encoding="utf-8").splitlines()[0]
        assert header == ",".join(fields), name


def _snapshot(directory: Path) -> dict[str, bytes]:
    return {
        p.relative_to(directory).as_posix(): p.read_bytes()
        for p in sorted(directory.rglob("*"))
        if p.is_file()
    }


def _previous_set_id(files: dict[str, bytes]) -> str:
    listing = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}
    return hashlib.sha256(canonical_json_bytes(listing)).hexdigest()[:16]


@pytest.mark.external_data
def test_divergent_existing_projection_is_not_overwritten(
    tmp_path: Path, inputs: dict[str, Any]
) -> None:
    _write(inputs, tmp_path)
    (tmp_path / COVERAGE_FILE).write_text("editado à mão\n", encoding="utf-8")
    before = _snapshot(tmp_path)

    with pytest.raises(ProfileReconciliationError, match="new-revision"):
        _write(inputs, tmp_path)
    assert _snapshot(tmp_path) == before


@pytest.mark.external_data
def test_refusal_happens_before_creating_anything(tmp_path: Path, inputs: dict[str, Any]) -> None:
    """M12: a recusa ocorre antes de qualquer escrita, inclusive ``mkdir`` de revisões."""
    out = tmp_path / "out"
    _write(inputs, out)
    (out / DIVERGENCE_FILE).write_bytes(b"outro\n")

    with pytest.raises(ProfileReconciliationError):
        _write(inputs, out)
    assert not (out / REVISIONS_DIR).exists()


@pytest.mark.external_data
def test_new_revision_preserves_the_previous_set_recoverably(
    tmp_path: Path, inputs: dict[str, Any]
) -> None:
    _write(inputs, tmp_path)
    (tmp_path / COVERAGE_FILE).write_text("revisão anterior\n", encoding="utf-8")
    previous = {
        name: (tmp_path / name).read_bytes()
        for name in (COVERAGE_FILE, DIVERGENCE_FILE, CORRESPONDENCE_FILE, MANIFEST_FILE)
    }

    _write(inputs, tmp_path, allow_new_revision=True)

    archive = tmp_path / REVISIONS_DIR / _previous_set_id(previous)
    assert {name: (archive / name).read_bytes() for name in previous} == previous
    record = json.loads((archive / ARCHIVE_RECORD_FILE).read_text(encoding="utf-8"))
    assert record["files"] == {
        name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        for name, data in previous.items()
    }
    assert (tmp_path / COVERAGE_FILE).read_text(encoding="utf-8").startswith("source_kind,")


@pytest.mark.external_data
def test_identical_regeneration_creates_no_revision(tmp_path: Path, inputs: dict[str, Any]) -> None:
    _write(inputs, tmp_path)
    _write(inputs, tmp_path, allow_new_revision=True)

    assert not (tmp_path / REVISIONS_DIR).exists()


@pytest.mark.external_data
def test_preexisting_revision_destination_with_other_content_is_refused(
    tmp_path: Path, inputs: dict[str, Any]
) -> None:
    _write(inputs, tmp_path)
    (tmp_path / COVERAGE_FILE).write_text("revisão anterior\n", encoding="utf-8")
    previous = {
        name: (tmp_path / name).read_bytes()
        for name in (COVERAGE_FILE, DIVERGENCE_FILE, CORRESPONDENCE_FILE, MANIFEST_FILE)
    }
    archive = tmp_path / REVISIONS_DIR / _previous_set_id(previous)
    archive.mkdir(parents=True)
    (archive / COVERAGE_FILE).write_text("conteúdo alheio\n", encoding="utf-8")
    before = _snapshot(tmp_path)

    with pytest.raises(ProfileReconciliationError, match="revisão"):
        _write(inputs, tmp_path, allow_new_revision=True)
    assert _snapshot(tmp_path) == before


@pytest.mark.external_data
def test_partial_write_failure_restores_the_previous_set(
    tmp_path: Path, inputs: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    _write(inputs, tmp_path)
    (tmp_path / COVERAGE_FILE).write_text("revisão anterior\n", encoding="utf-8")
    previous = {
        name: (tmp_path / name).read_bytes()
        for name in (COVERAGE_FILE, DIVERGENCE_FILE, CORRESPONDENCE_FILE, MANIFEST_FILE)
    }
    real_replace = os.replace

    def failing_replace(src: Any, dst: Any) -> None:
        if str(dst).endswith(DIVERGENCE_FILE):
            raise OSError("disco cheio (simulado)")
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", failing_replace)
    with pytest.raises(ProfileReconciliationError, match="revertida"):
        _write(inputs, tmp_path, allow_new_revision=True)
    monkeypatch.undo()

    assert {name: (tmp_path / name).read_bytes() for name in previous} == previous
    archive = tmp_path / REVISIONS_DIR / _previous_set_id(previous)
    assert {name: (archive / name).read_bytes() for name in previous} == previous
    assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]


@pytest.mark.external_data
def test_committed_e4_projections_match_regeneration(
    tmp_path: Path, inputs: dict[str, Any]
) -> None:
    _write(inputs, tmp_path)

    for name in (COVERAGE_FILE, DIVERGENCE_FILE, CORRESPONDENCE_FILE, MANIFEST_FILE):
        committed = (E4_DOCS / name).read_bytes().replace(b"\r\n", b"\n")
        assert committed == (tmp_path / name).read_bytes(), name


@pytest.mark.external_data
def test_cli_writes_only_to_the_explicit_output(tmp_path: Path) -> None:
    before = {p.name: p.read_bytes() for p in E1_PROJECTIONS.glob("*daiane*")}

    assert main(["--out", str(tmp_path / "e4")]) == 0
    assert (tmp_path / "e4" / MANIFEST_FILE).exists()
    assert {p.name: p.read_bytes() for p in E1_PROJECTIONS.glob("*daiane*")} == before


@pytest.mark.external_data
def test_returning_to_an_already_archived_set_reuses_the_identical_archive(
    tmp_path: Path, inputs: dict[str, Any]
) -> None:
    """Menor 7: arquivo de revisão idêntico já presente é aceito (A→B→A idempotente)."""
    _write(inputs, tmp_path)
    (tmp_path / COVERAGE_FILE).write_text("revisão anterior\n", encoding="utf-8")
    previous = _snapshot(tmp_path)
    _write(inputs, tmp_path, allow_new_revision=True)
    archive_before = _snapshot(tmp_path / REVISIONS_DIR)
    for name, data in previous.items():
        (tmp_path / name).write_bytes(data)

    _write(inputs, tmp_path, allow_new_revision=True)
    assert _snapshot(tmp_path / REVISIONS_DIR) == archive_before


@pytest.mark.external_data
def test_failed_write_removes_files_that_did_not_exist_before(
    tmp_path: Path, inputs: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Menor 7: na restauração, arquivo novo é removido e o anterior volta."""
    import os

    _write(inputs, tmp_path / "ref")
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / DIVERGENCE_FILE).write_bytes(b"anterior\n")
    real_replace = os.replace

    def failing_replace(src: Any, dst: Any) -> None:
        if str(dst).endswith(CORRESPONDENCE_FILE):
            raise OSError("falha simulada")
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", failing_replace)
    with pytest.raises(ProfileReconciliationError, match="revertida"):
        _write(inputs, tmp_path / "out", allow_new_revision=True)
    monkeypatch.undo()

    names = {p.name for p in (tmp_path / "out").iterdir() if p.is_file()}
    assert names == {DIVERGENCE_FILE}
    assert (tmp_path / "out" / DIVERGENCE_FILE).read_bytes() == b"anterior\n"
