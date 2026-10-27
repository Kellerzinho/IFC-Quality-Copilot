"""Reader de pacote local fixado (M1-06); pacotes SINTÉTICOS em ``tmp_path``.

Abrir falha por pacote ausente, inválido ou de formato incompatível; falha nunca vira
busca sem resultado, catálogo vazio, outra versão ou consulta pública.
"""

import hashlib
import json
import os
from pathlib import Path

import pytest

from src.domain_catalog.canonical import canonical_json_bytes
from src.domain_catalog.contracts import (
    BindingQuery,
    BindingRequest,
    CatalogQuery,
    CatalogReleaseRef,
)
from src.domain_catalog.errors import CatalogEntityNotFoundError, CatalogPackageError
from src.domain_catalog.package import MANIFEST_FILE, PackageLimits
from src.domain_catalog.reader import open_catalog
from tests.domain_catalog import factories as f
from tests.domain_catalog.factories import R


def _snapshot(directory: Path) -> dict[str, tuple[bytes, int]]:
    return {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in sorted(directory.iterdir())}


def _rewrite(
    directory: Path,
    name: str,
    data: bytes,
    ref: CatalogReleaseRef,
    entries: int | None = None,
) -> CatalogReleaseRef:
    """Troca um arquivo e regrava o manifesto coerente, devolvendo a nova referência."""
    (directory / name).write_bytes(data)
    manifest = json.loads((directory / MANIFEST_FILE).read_bytes())
    for item in manifest["files"]:
        if item["path"] == name:
            item["bytes"] = len(data)
            item["sha256"] = hashlib.sha256(data).hexdigest()
            item["entries"] = len(json.loads(data)) if entries is None else entries
    manifest_bytes = canonical_json_bytes(manifest)
    (directory / MANIFEST_FILE).write_bytes(manifest_bytes)
    return ref.model_copy(update={"manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest()})


def _reason(exc: pytest.ExceptionInfo[CatalogPackageError]) -> str:
    return exc.value.reason


# --- Abertura válida e consultas -----------------------------------------------------------


def test_valid_package_opens_and_identifies_release(tmp_path: Path) -> None:
    ref, path = f.write_synthetic_release(tmp_path)

    reader = open_catalog(ref, path)

    assert reader.ref == ref
    assert reader.describe().content_origin == "synthetic_fixture"
    assert reader.get_concept(R.METODO).code == "SYN_METODO"


def test_resolution_through_reader_carries_release_identity(tmp_path: Path) -> None:
    ref, path = f.write_synthetic_release(tmp_path)
    request = BindingRequest(
        ifc_schema="IFC4",
        facet="property",
        set_name="SYN_Conjunto",
        field_name="SYN_Metodo",
        entity="IfcSlab",
    )

    result = open_catalog(ref, path).resolve_binding(request)

    assert (result.status, result.binding_id, result.catalog) == ("exact", R.B_METODO_SLAB, ref)


def test_unknown_id_is_not_found_not_ambiguous(tmp_path: Path) -> None:
    ref, path = f.write_synthetic_release(tmp_path)

    with pytest.raises(CatalogEntityNotFoundError):
        open_catalog(ref, path).get_concept("urn:uuid:00000000-0000-4000-8000-0000000000ff")


def test_capability_of_unimplemented_operation_is_unsupported(tmp_path: Path) -> None:
    ref, path = f.write_synthetic_release(tmp_path)

    capability = open_catalog(ref, path).get_capability("formwork_area_from_geometry")

    assert capability.status == "unsupported"


def test_text_search_ignores_case_and_accents_only_to_find_candidates(tmp_path: Path) -> None:
    ref, path = f.write_synthetic_release(tmp_path)
    reader = open_catalog(ref, path)

    page = reader.search(CatalogQuery(text="acabamento"))

    assert [item.code for item in page.items] == ["SYN_ACABAMENTO_PAREDE", "SYN_ACABAMENTO_PISO"]
    assert page.total == 2
    assert reader.get_binding(R.B_ACAB_PISO).field_name == "SYN_Acabamento"


def test_search_filters_and_paginates_deterministically(tmp_path: Path) -> None:
    ref, path = f.write_synthetic_release(tmp_path)
    reader = open_catalog(ref, path)

    covering = reader.search(CatalogQuery(entity="IfcCovering"))
    first = reader.search(CatalogQuery(limit=3))
    second = reader.search(CatalogQuery(offset=3, limit=3))

    assert {item.code for item in covering.items} == {
        "SYN_ACABAMENTO_PISO",
        "SYN_ACABAMENTO_PAREDE",
    }
    assert first.total == second.total == 9
    assert not {i.concept_id for i in first.items} & {i.concept_id for i in second.items}


def test_list_bindings_filters_by_concept_and_exact_path(tmp_path: Path) -> None:
    ref, path = f.write_synthetic_release(tmp_path)
    reader = open_catalog(ref, path)

    by_concept = reader.list_bindings(BindingQuery(concept_id=R.METODO))
    by_path = reader.list_bindings(BindingQuery(set_name="SYN_PsetA", field_name="Status"))

    assert [b.id for b in by_concept.items] == [R.B_METODO_SLAB, R.B_METODO_COLUMN]
    assert [b.id for b in by_path.items] == [R.B_STATUS_A]


def test_queries_do_not_change_release_bytes(tmp_path: Path) -> None:
    ref, path = f.write_synthetic_release(tmp_path)
    before = _snapshot(path)
    reader = open_catalog(ref, path)
    reader.search(CatalogQuery(text="metodo"))
    reader.list_bindings(BindingQuery())
    reader.resolve_binding(BindingRequest(ifc_schema="IFC4", facet="property", field_name="Status"))

    assert _snapshot(path) == before


def test_reader_keeps_the_release_it_opened(tmp_path: Path) -> None:
    ref, path = f.write_synthetic_release(tmp_path)
    reader = open_catalog(ref, path)
    concepts = json.loads((path / "concepts.json").read_bytes())
    concepts[0]["code"] = "ALTERADO_DEPOIS"
    (path / "concepts.json").write_bytes(canonical_json_bytes(concepts))

    assert reader.get_concept(concepts[0]["id"]).code != "ALTERADO_DEPOIS"
    with pytest.raises(CatalogPackageError) as exc:
        open_catalog(ref, path)
    assert _reason(exc) == "integrity"


# --- Falhas que bloqueiam a abertura -------------------------------------------------------


def test_wrong_expected_hash_blocks_opening(tmp_path: Path) -> None:
    ref, path = f.write_synthetic_release(tmp_path)

    with pytest.raises(CatalogPackageError) as exc:
        open_catalog(ref.model_copy(update={"manifest_sha256": "0" * 64}), path)

    assert _reason(exc) == "integrity"


def test_reference_to_other_version_blocks_opening(tmp_path: Path) -> None:
    ref, path = f.write_synthetic_release(tmp_path)

    with pytest.raises(CatalogPackageError) as exc:
        open_catalog(ref.model_copy(update={"version": "1.0.1"}), path)

    assert _reason(exc) == "integrity"


def test_missing_release_never_falls_back_to_another_version(tmp_path: Path) -> None:
    ref, _ = f.write_synthetic_release(tmp_path, version="1.0.0")

    with pytest.raises(CatalogPackageError) as exc:
        open_catalog(ref.model_copy(update={"version": "2.0.0"}), tmp_path / "2.0.0")

    assert _reason(exc) == "not_found"


def test_tampered_data_file_blocks_opening(tmp_path: Path) -> None:
    ref, path = f.write_synthetic_release(tmp_path)
    data = (path / "concepts.json").read_bytes()
    (path / "concepts.json").write_bytes(data.replace(b"SYN_METODO", b"SYN_METODX"))

    with pytest.raises(CatalogPackageError) as exc:
        open_catalog(ref, path)

    assert _reason(exc) == "integrity"


@pytest.mark.parametrize("extra", ["leia-me.txt", "concepts.json.bak"])
def test_unexpected_file_blocks_opening(tmp_path: Path, extra: str) -> None:
    ref, path = f.write_synthetic_release(tmp_path)
    (path / extra).write_text("x", encoding="utf-8")

    with pytest.raises(CatalogPackageError) as exc:
        open_catalog(ref, path)

    assert _reason(exc) == "layout"


def test_subdirectory_blocks_opening(tmp_path: Path) -> None:
    ref, path = f.write_synthetic_release(tmp_path)
    (path / "anexos").mkdir()

    with pytest.raises(CatalogPackageError) as exc:
        open_catalog(ref, path)

    assert _reason(exc) == "layout"


def test_symlinked_data_file_blocks_opening(tmp_path: Path) -> None:
    ref, path = f.write_synthetic_release(tmp_path)
    outside = tmp_path / "fora.json"
    outside.write_bytes((path / "units.json").read_bytes())
    (path / "units.json").unlink()
    try:
        os.symlink(outside, path / "units.json")
    except OSError:
        pytest.skip("criação de link simbólico indisponível neste ambiente")

    with pytest.raises(CatalogPackageError) as exc:
        open_catalog(ref, path)

    assert _reason(exc) == "layout"


@pytest.mark.parametrize("bad_path", ["../concepts.json", "C:/concepts.json", "sub/concepts.json"])
def test_manifest_paths_outside_package_are_refused(tmp_path: Path, bad_path: str) -> None:
    ref, path = f.write_synthetic_release(tmp_path)
    manifest = json.loads((path / MANIFEST_FILE).read_bytes())
    manifest["files"][0]["path"] = bad_path
    manifest_bytes = canonical_json_bytes(manifest)
    (path / MANIFEST_FILE).write_bytes(manifest_bytes)
    crafted = ref.model_copy(update={"manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest()})

    with pytest.raises(CatalogPackageError) as exc:
        open_catalog(crafted, path)

    assert _reason(exc) == "format"


def test_unknown_format_version_blocks_opening(tmp_path: Path) -> None:
    ref, path = f.write_synthetic_release(tmp_path)
    manifest = json.loads((path / MANIFEST_FILE).read_bytes())
    manifest["format_version"] = 2
    manifest_bytes = canonical_json_bytes(manifest)
    (path / MANIFEST_FILE).write_bytes(manifest_bytes)
    crafted = ref.model_copy(update={"manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest()})

    with pytest.raises(CatalogPackageError, match="formato") as exc:
        open_catalog(crafted, path)

    assert _reason(exc) == "format"


@pytest.mark.parametrize("version", [True, 1.0], ids=["booleano", "float"])
def test_format_version_must_be_the_integer_one(tmp_path: Path, version: object) -> None:
    # Revisão E1-09: ``true == 1`` e ``1.0 == 1`` em Python, mas o formato pede inteiro.
    ref, path = f.write_synthetic_release(tmp_path)
    manifest = json.loads((path / MANIFEST_FILE).read_bytes())
    manifest["format_version"] = version
    manifest_bytes = canonical_json_bytes(manifest)
    (path / MANIFEST_FILE).write_bytes(manifest_bytes)
    crafted = ref.model_copy(update={"manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest()})

    with pytest.raises(CatalogPackageError, match="não suportado") as exc:
        open_catalog(crafted, path)

    assert _reason(exc) == "format"


def test_non_canonical_manifest_blocks_opening(tmp_path: Path) -> None:
    ref, path = f.write_synthetic_release(tmp_path)
    pretty = json.dumps(json.loads((path / MANIFEST_FILE).read_bytes()), indent=2).encode()
    (path / MANIFEST_FILE).write_bytes(pretty)
    crafted = ref.model_copy(update={"manifest_sha256": hashlib.sha256(pretty).hexdigest()})

    with pytest.raises(CatalogPackageError) as exc:
        open_catalog(crafted, path)

    assert _reason(exc) == "format"


def test_manifest_entry_count_must_match_data_file(tmp_path: Path) -> None:
    ref, path = f.write_synthetic_release(tmp_path)
    manifest = json.loads((path / MANIFEST_FILE).read_bytes())
    for item in manifest["files"]:
        if item["path"] == "bindings.json":
            item["entries"] += 1
    manifest_bytes = canonical_json_bytes(manifest)
    (path / MANIFEST_FILE).write_bytes(manifest_bytes)
    crafted = ref.model_copy(update={"manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest()})

    with pytest.raises(CatalogPackageError, match="entradas") as exc:
        open_catalog(crafted, path)

    assert _reason(exc) == "format"


@pytest.mark.parametrize(
    "payload",
    [b'[{"id":"x","id":"y"}]\n', b"[NaN]\n"],
    ids=["chave-duplicada", "nan"],
)
def test_ambiguous_json_in_data_file_blocks_opening(tmp_path: Path, payload: bytes) -> None:
    ref, path = f.write_synthetic_release(tmp_path)
    crafted = _rewrite(path, "units.json", payload, ref)

    with pytest.raises(CatalogPackageError) as exc:
        open_catalog(crafted, path)

    assert _reason(exc) == "format"


@pytest.mark.parametrize(
    "payload",
    [
        b'["\\ud800"]\n',
        b"[" + b"1" * 5000 + b"]\n",
        b"[" * 5000 + b"0" + b"]" * 5000 + b"\n",
    ],
    ids=["surrogate-isolado", "inteiro-excessivo", "aninhamento-excessivo"],
)
def test_malformed_json_in_data_file_is_a_package_error(tmp_path: Path, payload: bytes) -> None:
    # Revisão E1-04: escapavam UnicodeEncodeError, ValueError e RecursionError, com
    # tamanhos e hashes coerentes e arquivos muito abaixo dos limites.
    ref, path = f.write_synthetic_release(tmp_path)
    crafted = _rewrite(path, "units.json", payload, ref, entries=1)

    with pytest.raises(CatalogPackageError) as exc:
        open_catalog(crafted, path)

    assert _reason(exc) == "format"


@pytest.mark.skipif(os.name != "nt", reason="bloqueio de compartilhamento exclusivo do Windows")
def test_locked_manifest_is_an_io_package_error(tmp_path: Path) -> None:
    # Revisão E1-04: manifesto aberto por outro handle sem compartilhamento (lock real).
    import ctypes
    from ctypes import wintypes

    ref, path = f.write_synthetic_release(tmp_path)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    generic_read, no_sharing, open_existing = 0x80000000, 0, 3
    handle = kernel.CreateFileW(
        str(path / MANIFEST_FILE), generic_read, no_sharing, None, open_existing, 0, None
    )
    assert handle != ctypes.c_void_p(-1).value, ctypes.get_last_error()
    try:
        with pytest.raises(CatalogPackageError) as exc:
            open_catalog(ref, path)
    finally:
        kernel.CloseHandle(handle)

    assert _reason(exc) == "io"


def _denied(target: Path) -> PermissionError:
    return PermissionError(13, "acesso negado (simulado no teste)", str(target))


@pytest.mark.parametrize("operation", ["is_dir", "scandir", "open"])
def test_filesystem_failure_is_an_io_package_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    # Cada operação de disco da abertura falha com causa tipada, nunca com OSError cru.
    ref, path = f.write_synthetic_release(tmp_path)
    data_file = path / "units.json"
    if operation == "is_dir":
        original_is_dir = Path.is_dir

        def is_dir(self: Path, *args: object, **kwargs: object) -> bool:
            if self == path:
                raise _denied(self)
            return original_is_dir(self, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(Path, "is_dir", is_dir)
    elif operation == "scandir":
        original_scandir = os.scandir

        def scandir(target: Path) -> object:
            if Path(target) == path:
                raise _denied(Path(target))
            return original_scandir(target)

        monkeypatch.setattr(os, "scandir", scandir)
    else:
        original_open = Path.open

        def open_(self: Path, *args: object, **kwargs: object) -> object:
            if self == data_file:
                raise _denied(self)
            return original_open(self, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(Path, "open", open_)

    with pytest.raises(CatalogPackageError) as exc:
        open_catalog(ref, path)

    assert _reason(exc) == "io"
    assert isinstance(exc.value.__cause__, PermissionError)


def _rewrite_manifest(path: Path, ref: CatalogReleaseRef, **changes: object) -> CatalogReleaseRef:
    """Altera campos do manifesto e devolve a referência coerente com os novos bytes."""
    manifest = json.loads((path / MANIFEST_FILE).read_bytes())
    manifest.update(changes)
    manifest_bytes = canonical_json_bytes(manifest)
    (path / MANIFEST_FILE).write_bytes(manifest_bytes)
    return ref.model_copy(update={"manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest()})


@pytest.mark.parametrize(
    "schemas", [["IFC2X3"], ["IFC2X3", "IFC4"], []], ids=["contraditorio", "a-mais", "vazio"]
)
def test_manifest_schema_summary_must_match_the_bindings(
    tmp_path: Path, schemas: list[str]
) -> None:
    # Revisão E1-07: o manifesto dizia IFC2X3 enquanto os bindings só declaravam IFC4.
    ref, path = f.write_synthetic_release(tmp_path, f.minimal_content())
    crafted = _rewrite_manifest(path, ref, declared_schemas=schemas)

    with pytest.raises(CatalogPackageError, match="schemas") as exc:
        open_catalog(crafted, path)

    assert _reason(exc) == "format"


def test_manifest_profile_summary_must_match_the_memberships(tmp_path: Path) -> None:
    ref, path = f.write_synthetic_release(tmp_path, f.minimal_content())
    crafted = _rewrite_manifest(path, ref, profiles=["perfil-sem-participacao"])

    with pytest.raises(CatalogPackageError, match="perfis") as exc:
        open_catalog(crafted, path)

    assert _reason(exc) == "format"


def test_entities_out_of_canonical_id_order_are_refused(tmp_path: Path) -> None:
    # O formato publica entidades em ordem de ID; outra ordem é outra forma de bytes.
    ref, path = f.write_synthetic_release(tmp_path)
    bindings = json.loads((path / "bindings.json").read_bytes())
    crafted = _rewrite(path, "bindings.json", canonical_json_bytes(bindings[::-1]), ref)

    with pytest.raises(CatalogPackageError, match="ordem") as exc:
        open_catalog(crafted, path)

    assert _reason(exc) == "format"


def test_draft_entity_inside_package_blocks_opening(tmp_path: Path) -> None:
    ref, path = f.write_synthetic_release(tmp_path)
    units = json.loads((path / "units.json").read_bytes())
    units[0]["lifecycle"] = "draft"
    crafted = _rewrite(path, "units.json", canonical_json_bytes(units), ref)

    with pytest.raises(CatalogPackageError) as exc:
        open_catalog(crafted, path)

    assert _reason(exc) == "content"
    assert {issue.code for issue in exc.value.issues} == {"lifecycle_not_publishable"}


def test_unknown_field_in_entity_blocks_opening(tmp_path: Path) -> None:
    ref, path = f.write_synthetic_release(tmp_path)
    policies = [{"id": "urn:uuid:00000000-0000-4000-8000-0000000000d9", "codigo": "os:system"}]
    crafted = _rewrite(path, "evidence_policies.json", canonical_json_bytes(policies), ref)

    with pytest.raises(CatalogPackageError) as exc:
        open_catalog(crafted, path)

    assert _reason(exc) == "content"


def test_file_above_limit_is_refused_before_parsing(tmp_path: Path) -> None:
    ref, path = f.write_synthetic_release(tmp_path)

    with pytest.raises(CatalogPackageError) as exc:
        open_catalog(ref, path, limits=PackageLimits(max_file_bytes=64))

    assert _reason(exc) == "limit"
