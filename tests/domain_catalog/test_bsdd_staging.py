"""Staging bSDD: normalização, cadeia raw→normalized, reabertura verificada e diff (E4, M1-10).

Fixtures SINTÉTICAS. A aquisição bruta guarda os bytes lidos; a normalização
``ifcqc-bsdd-normalization-1`` materializa ``dictionary.normalized.json`` e o
``CatalogContent`` aponta esse artefato. Reordenação e espaços mudam o hash bruto e o
recibo, mas não o conteúdo candidato.
"""

import hashlib
import json
import socket
from pathlib import Path
from typing import Any

import pytest

from src.domain_catalog.canonical import canonical_json_bytes
from src.domain_catalog.importers.bsdd import (
    BSDDSnapshotError,
    diff_bsdd_staging,
    import_bsdd_snapshot,
    load_bsdd_snapshot,
    read_bsdd_staging,
    write_bsdd_staging,
)
from src.domain_catalog.importers.bsdd_models import BSDDImportResult, SnapshotLimits
from tests.domain_catalog.test_bsdd_import import payload, source


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("staging bSDD tentou abrir conexão de rede")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def imported(
    tmp_path: Path, document: Any, name: str, *, indent: int | None = 2, prior: Any = None
) -> BSDDImportResult:
    path = tmp_path / name
    path.write_text(json.dumps(document, ensure_ascii=False, indent=indent), encoding="utf-8")
    snapshot = load_bsdd_snapshot(path, source=source(), limits=SnapshotLimits())
    return import_bsdd_snapshot(snapshot, prior=prior)


def reordered(document: dict[str, Any]) -> dict[str, Any]:
    """Mesmo conteúdo com classes, propriedades e associações em outra ordem."""
    other = json.loads(json.dumps(document))
    other["Classes"].reverse()
    other["Properties"].reverse()
    for item in other["Classes"]:
        item.get("ClassProperties", []).reverse()
    return {key: other[key] for key in reversed(list(other))}


def content_hash(result: BSDDImportResult) -> str:
    assert result.content is not None
    return hashlib.sha256(canonical_json_bytes(result.content.model_dump(mode="json"))).hexdigest()


def test_reordering_and_whitespace_keep_semantics_and_candidates(tmp_path: Path) -> None:
    first = imported(tmp_path, payload(), "a.json")
    second = imported(tmp_path, reordered(payload()), "b.json", indent=None)

    assert first.acquisition.raw_sha256 != second.acquisition.raw_sha256
    assert first.staging.semantic_sha256 == second.staging.semantic_sha256
    assert first.content == second.content
    assert content_hash(first) == content_hash(second)
    assert first.acquisition.links != second.acquisition.links


def test_content_source_artifact_describes_the_normalized_bytes(tmp_path: Path) -> None:
    result = imported(tmp_path, payload(), "a.json")
    assert result.content is not None
    artifact = result.content.source_artifacts[0]
    normalized = result.normalized_bytes

    assert (
        artifact.sha256 == hashlib.sha256(normalized).hexdigest() == result.staging.semantic_sha256
    )
    assert artifact.size_bytes == len(normalized)
    assert artifact.location == "dictionary.normalized.json"
    assert artifact.sha256 != result.acquisition.raw_sha256
    document = json.loads(normalized)
    for assertion in result.content.source_assertions:
        pointer = assertion.locator.row_ref
        assert pointer is not None
        node: Any = document
        for part in pointer.strip("/").split("/"):
            node = node[int(part)] if isinstance(node, list) else node[part]
        assert node["Code"] == assertion.target_identifier_literal


def test_normalized_bytes_are_canonical_and_sorted_by_identity(tmp_path: Path) -> None:
    result = imported(tmp_path, reordered(payload()), "a.json")
    document = json.loads(result.normalized_bytes)

    assert canonical_json_bytes(document) == result.normalized_bytes
    codes = [item["Code"].casefold() for item in document["Properties"]]
    assert codes == sorted(codes)
    first_values = [
        v["Code"] for v in document["Properties"][codes.index("syn-acabamento")]["AllowedValues"]
    ]
    assert first_values == ["a", "b"]


def test_written_staging_reopens_identically(tmp_path: Path) -> None:
    result = imported(tmp_path, payload(), "a.json")
    manifest = write_bsdd_staging(result, tmp_path / "out")
    reopened = read_bsdd_staging(tmp_path / "out")

    assert reopened == result
    assert (tmp_path / "out" / "source.raw.json").read_bytes() == (tmp_path / "a.json").read_bytes()
    names = {item.path for item in manifest.files}
    assert {
        "source.raw.json",
        "dictionary.normalized.json",
        "staging.json",
        "report.json",
        "acquisition.json",
        "candidates.json",
    } <= names


def test_writer_never_overwrites_an_existing_staging(tmp_path: Path) -> None:
    result = imported(tmp_path, payload(), "a.json")
    write_bsdd_staging(result, tmp_path / "out")

    with pytest.raises(FileExistsError):
        write_bsdd_staging(result, tmp_path / "out")


@pytest.mark.parametrize(
    "name", ["dictionary.normalized.json", "source.raw.json", "candidates.json"]
)
def test_tampered_staging_file_is_refused(tmp_path: Path, name: str) -> None:
    result = imported(tmp_path, payload(), "a.json")
    write_bsdd_staging(result, tmp_path / "out")
    target = tmp_path / "out" / name
    target.write_bytes(target.read_bytes().replace(b"Acabamento", b"Acabamentx", 1))

    with pytest.raises(BSDDSnapshotError) as error:
        read_bsdd_staging(tmp_path / "out")
    assert error.value.code == "staging_integrity"


def test_tampered_normalized_with_recomputed_manifest_is_refused(tmp_path: Path) -> None:
    result = imported(tmp_path, payload(), "a.json")
    write_bsdd_staging(result, tmp_path / "out")
    out = tmp_path / "out"
    normalized = out / "dictionary.normalized.json"
    normalized.write_bytes(normalized.read_bytes().replace(b"Acabamento A", b"Acabamento Z"))
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    for item in manifest["files"]:
        if item["path"] == "dictionary.normalized.json":
            data = normalized.read_bytes()
            item["sha256"], item["bytes"] = hashlib.sha256(data).hexdigest(), len(data)
    (out / "manifest.json").write_bytes(canonical_json_bytes(manifest))

    with pytest.raises(BSDDSnapshotError) as error:
        read_bsdd_staging(out)
    assert error.value.code == "staging_integrity"


def test_raw_to_normalized_link_bound_to_the_wrong_entity_is_refused(tmp_path: Path) -> None:
    result = imported(tmp_path, payload(), "a.json")
    write_bsdd_staging(result, tmp_path / "out")
    out = tmp_path / "out"
    acquisition = json.loads((out / "acquisition.json").read_text(encoding="utf-8"))
    links = acquisition["links"]
    links[0]["normalized_pointer"], links[1]["normalized_pointer"] = (
        links[1]["normalized_pointer"],
        links[0]["normalized_pointer"],
    )
    data = canonical_json_bytes(acquisition)
    (out / "acquisition.json").write_bytes(data)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    for item in manifest["files"]:
        if item["path"] == "acquisition.json":
            item["sha256"], item["bytes"] = hashlib.sha256(data).hexdigest(), len(data)
    (out / "manifest.json").write_bytes(canonical_json_bytes(manifest))

    with pytest.raises(BSDDSnapshotError) as error:
        read_bsdd_staging(out)
    assert error.value.code == "staging_integrity"


def test_identical_reimport_produces_no_delta_and_same_ids(tmp_path: Path) -> None:
    first = imported(tmp_path, payload(), "a.json")
    again = imported(tmp_path, payload(), "b.json", prior=first.staging)
    diff = diff_bsdd_staging(first.staging, again.staging)

    assert diff.is_empty
    assert first.content == again.content
    assert again.migrations == ()


def test_same_version_with_different_semantics_conflicts(tmp_path: Path) -> None:
    first = imported(tmp_path, payload(), "a.json")
    changed = payload()
    changed["Properties"][2]["Name"] = "Ativo (renomeado)"

    with pytest.raises(BSDDSnapshotError) as error:
        imported(tmp_path, changed, "b.json", prior=first.staging)
    assert error.value.code == "version_conflict"


def test_new_version_keeps_origin_key_creates_new_candidate_and_pending_migration(
    tmp_path: Path,
) -> None:
    first = imported(tmp_path, payload(), "a.json")
    newer = payload()
    newer["DictionaryVersion"] = "1.1"
    newer["Properties"][2]["Name"] = "Ativo (renomeado)"
    del newer["Properties"][3]
    newer["Properties"].append({"Code": "syn-novo", "Name": "Novo", "DataType": "String"})
    second = imported(tmp_path, newer, "b.json", prior=first.staging)
    diff = diff_bsdd_staging(first.staging, second.staging)

    assert {e.code_literal for e in diff.added} == {"syn-novo"}
    assert {e.code_literal for e in diff.removed} == {"syn-pavimentos"}
    changed = {c.code_literal: c.fields for c in diff.changed}
    assert changed["syn-ativo"] == ("Name",)
    old = first.staging.entity("property", "syn-ativo")
    new = second.staging.entity("property", "syn-ativo")
    assert old.origin_key == new.origin_key
    assert old.source_key != new.source_key
    assert first.content is not None
    assert second.content is not None
    assert not {c.id for c in first.content.concepts} & {c.id for c in second.content.concepts}
    migration = next(m for m in second.migrations if m.origin_key == old.origin_key)
    assert (migration.from_source_key, migration.to_source_key, migration.status) == (
        old.source_key,
        new.source_key,
        "pending_curation",
    )


def test_label_only_change_is_reported_as_changed_field_not_as_new_entity(tmp_path: Path) -> None:
    first = imported(tmp_path, payload(), "a.json")
    newer = payload()
    newer["DictionaryVersion"] = "2.0"
    newer["Properties"][0]["AllowedValues"][0]["Value"] = "Acabamento A (rótulo novo)"
    second = imported(tmp_path, newer, "b.json", prior=first.staging)
    diff = diff_bsdd_staging(first.staging, second.staging)

    assert not diff.added
    assert not diff.removed
    assert {c.code_literal: c.fields for c in diff.changed}["syn-acabamento"] == ("AllowedValues",)


# --- Retomada 23/10: escrita atômica, erros de reabertura, âncora do prior (M6–M9) -------


def test_failed_verification_leaves_no_staging_and_no_temporary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M6: verificação pós-escrita falha → destino não aparece, temporário removido."""
    import src.domain_catalog.importers.bsdd as bsdd_module

    result = imported(tmp_path, payload(), "a.json")

    def broken(path: Path, **kwargs: object) -> BSDDImportResult:
        raise BSDDSnapshotError("staging_integrity", "falha simulada na reabertura")

    monkeypatch.setattr(bsdd_module, "read_bsdd_staging", broken)
    with pytest.raises(BSDDSnapshotError) as error:
        write_bsdd_staging(result, tmp_path / "out")
    assert error.value.code == "staging_integrity"
    assert not (tmp_path / "out").exists()
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".out")]


def test_failed_file_write_leaves_no_partial_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = imported(tmp_path, payload(), "a.json")
    real_write = Path.write_bytes

    def failing(self: Path, data: bytes) -> int:
        if self.name == "report.json":
            raise OSError("disco cheio (simulado)")
        return real_write(self, data)

    monkeypatch.setattr(Path, "write_bytes", failing)
    with pytest.raises(BSDDSnapshotError) as error:
        write_bsdd_staging(result, tmp_path / "out")
    monkeypatch.undo()
    assert error.value.code == "staging_write_failed"
    assert not (tmp_path / "out").exists()
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".out")]


def test_existing_destination_is_left_byte_identical(tmp_path: Path) -> None:
    result = imported(tmp_path, payload(), "a.json")
    out = tmp_path / "out"
    out.mkdir()
    (out / "anterior.txt").write_bytes(b"staging anterior")

    with pytest.raises(FileExistsError):
        write_bsdd_staging(result, out)
    assert [p.name for p in out.iterdir()] == ["anterior.txt"]
    assert (out / "anterior.txt").read_bytes() == b"staging anterior"


def test_rewrite_of_the_same_result_is_byte_identical(tmp_path: Path) -> None:
    result = imported(tmp_path, payload(), "a.json")
    write_bsdd_staging(result, tmp_path / "one")
    write_bsdd_staging(read_bsdd_staging(tmp_path / "one"), tmp_path / "two")

    one = {p.name: p.read_bytes() for p in (tmp_path / "one").iterdir()}
    two = {p.name: p.read_bytes() for p in (tmp_path / "two").iterdir()}
    assert one == two


def _with_prior(tmp_path: Path) -> tuple[BSDDImportResult, BSDDImportResult]:
    first = imported(tmp_path, payload(), "a.json")
    newer = payload()
    newer["DictionaryVersion"] = "2.0"
    return first, imported(tmp_path, newer, "b.json", prior=first.staging)


def test_missing_listed_file_is_an_integrity_error(tmp_path: Path) -> None:
    """M7: arquivo listado ausente não escapa como OSError."""
    _, second = _with_prior(tmp_path)
    write_bsdd_staging(second, tmp_path / "out")
    (tmp_path / "out" / "diff.json").unlink()

    with pytest.raises(BSDDSnapshotError) as error:
        read_bsdd_staging(tmp_path / "out")
    assert error.value.code == "staging_integrity"


def test_invalid_prior_with_consistent_manifest_is_an_integrity_error(tmp_path: Path) -> None:
    """M7: prior.staging.json inválido (manifesto recalculado) não escapa como ValidationError."""
    _, second = _with_prior(tmp_path)
    out = tmp_path / "out"
    write_bsdd_staging(second, out)
    data = canonical_json_bytes({"profile": "outro"})
    (out / "prior.staging.json").write_bytes(data)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    for item in manifest["files"]:
        if item["path"] == "prior.staging.json":
            item["sha256"], item["bytes"] = hashlib.sha256(data).hexdigest(), len(data)
    (out / "manifest.json").write_bytes(canonical_json_bytes(manifest))

    with pytest.raises(BSDDSnapshotError) as error:
        read_bsdd_staging(out)
    assert error.value.code == "staging_integrity"


def test_prior_consistency_is_not_authenticity_unless_anchored(tmp_path: Path) -> None:
    """M8: prior forjado e regravado de modo consistente passa na consistência interna;
    só a âncora externa (hash semântico do prior conferido por quem chama) o recusa."""
    first, _ = _with_prior(tmp_path)
    forged_doc = payload()
    forged_doc["DictionaryName"] = "Prior forjado"
    forged = imported(tmp_path, forged_doc, "forjado.json")
    newer = payload()
    newer["DictionaryVersion"] = "2.0"
    result = imported(tmp_path, newer, "b.json", prior=forged.staging)
    write_bsdd_staging(result, tmp_path / "out")

    assert read_bsdd_staging(tmp_path / "out").prior == forged.staging
    with pytest.raises(BSDDSnapshotError) as error:
        read_bsdd_staging(
            tmp_path / "out", expected_prior_semantic_sha256=first.staging.semantic_sha256
        )
    assert error.value.code == "staging_integrity"
    assert (
        read_bsdd_staging(
            tmp_path / "out", expected_prior_semantic_sha256=forged.staging.semantic_sha256
        ).prior
        == forged.staging
    )


def test_prior_anchor_without_prior_is_refused(tmp_path: Path) -> None:
    first = imported(tmp_path, payload(), "a.json")
    write_bsdd_staging(first, tmp_path / "out")

    with pytest.raises(BSDDSnapshotError) as error:
        read_bsdd_staging(tmp_path / "out", expected_prior_semantic_sha256="0" * 64)
    assert error.value.code == "staging_integrity"


def test_null_and_empty_class_properties_are_equivalent_but_absent_is_kept(
    tmp_path: Path,
) -> None:
    """M9: ``ClassProperties: null`` normaliza para ``[]``; chave ausente é preservada como
    ausência (hash semântico distinto), sem fabricar lista."""
    empty, null, absent = payload(), payload(), payload()
    empty["Classes"][1]["ClassProperties"] = []
    null["Classes"][1]["ClassProperties"] = None
    absent["Classes"][1].pop("ClassProperties", None)
    results = [
        imported(tmp_path, doc, f"{name}.json")
        for name, doc in (("empty", empty), ("null", null), ("absent", absent))
    ]

    assert results[0].staging.semantic_sha256 == results[1].staging.semantic_sha256
    assert results[0].content == results[1].content
    assert results[2].staging.semantic_sha256 != results[0].staging.semantic_sha256
    absent_content, empty_content = results[2].content, results[0].content
    assert absent_content is not None
    assert empty_content is not None
    assert absent_content.concepts == empty_content.concepts
    assert absent_content.source_artifacts[0].sha256 != empty_content.source_artifacts[0].sha256


def test_unexpected_exception_also_removes_the_temporary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Menor 5: qualquer exceção remove o temporário e propaga sem destino parcial."""
    import src.domain_catalog.importers.bsdd as bsdd_module

    result = imported(tmp_path, payload(), "a.json")

    def boom(path: Path, **kwargs: object) -> BSDDImportResult:
        raise RuntimeError("falha inesperada simulada")

    monkeypatch.setattr(bsdd_module, "read_bsdd_staging", boom)
    with pytest.raises(RuntimeError, match="inesperada"):
        write_bsdd_staging(result, tmp_path / "out")
    assert not (tmp_path / "out").exists()
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".out")]
