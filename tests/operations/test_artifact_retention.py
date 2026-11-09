"""Retenção local verificada de IFC/IDS e de pacotes de catálogo; inspeção sem apagar."""

import hashlib
import os
from pathlib import Path

import pytest

from src.artifacts.contracts import ArtifactError, RetainedCatalogRef
from src.artifacts.storage import LocalArtifactStore, SourceLimits
from src.domain_catalog.contracts import CatalogReleaseRef
from src.domain_catalog.errors import CatalogPackageError
from src.operations.contracts import SourceArtifactRef
from tests.domain_catalog import factories as f

IFC_BYTES = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"


def _write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _ref_for(retained_sha: str, size: int, role: str = "ifc") -> SourceArtifactRef:
    return SourceArtifactRef(
        project_id="1111aaaa-1111-4111-8111-111111111111",  # type: ignore[arg-type]
        model_id="2222aaaa-2222-4222-8222-222222222222",  # type: ignore[arg-type]
        source_id="3333aaaa-3333-4333-8333-333333333333",  # type: ignore[arg-type]
        revision=1,
        role=role,  # type: ignore[arg-type]
        sha256=retained_sha,
        size_bytes=size,
        display_name="modelo.ifc",
        storage_key=f"s/{role}/{retained_sha}",
    )


def test_retained_source_keeps_exact_bytes_under_hash_key(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "a")
    source = _write(tmp_path / "in" / "modelo.ifc", IFC_BYTES)

    retained = store.retain_source(source, "ifc")

    digest = hashlib.sha256(IFC_BYTES).hexdigest()
    assert (retained.sha256, retained.size_bytes) == (digest, len(IFC_BYTES))
    assert retained.storage_key == f"s/ifc/{digest}"
    assert retained.display_name == "modelo.ifc"
    assert store.read_verified_source(_ref_for(digest, len(IFC_BYTES))).read_bytes() == IFC_BYTES
    again = store.retain_source(_write(tmp_path / "in2" / "copia.ifc", IFC_BYTES), "ifc")
    assert again.storage_key == retained.storage_key
    assert again.display_name == "copia.ifc"
    assert store.inspect_orphans({retained.storage_key}).staging == ()


def test_input_must_be_regular_existing_file(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "a")
    with pytest.raises(ArtifactError) as missing:
        store.retain_source(tmp_path / "nao-existe.ifc", "ifc")
    assert missing.value.reason == "artifact_unavailable"
    (tmp_path / "pasta.ifc").mkdir()
    with pytest.raises(ArtifactError) as directory:
        store.retain_source(tmp_path / "pasta.ifc", "ifc")
    assert directory.value.reason == "unsafe_source"


def test_symlinked_input_is_refused(tmp_path: Path) -> None:
    target = _write(tmp_path / "real.ifc", IFC_BYTES)
    link = tmp_path / "link.ifc"
    try:
        os.symlink(target, link)
    except OSError:
        pytest.skip("criação de link simbólico sem privilégio neste Windows")
    with pytest.raises(ArtifactError) as refused:
        LocalArtifactStore(tmp_path / "a").retain_source(link, "ifc")
    assert refused.value.reason == "unsafe_source"


def test_size_limit_allows_equality_and_refuses_one_more_byte(tmp_path: Path) -> None:
    store = LocalArtifactStore(
        tmp_path / "a", limits=SourceLimits(max_ifc_bytes=len(IFC_BYTES), max_ids_bytes=4)
    )
    assert store.retain_source(_write(tmp_path / "ok.ifc", IFC_BYTES), "ifc").size_bytes == len(
        IFC_BYTES
    )
    with pytest.raises(ArtifactError) as refused:
        store.retain_source(_write(tmp_path / "big.ifc", IFC_BYTES + b"x"), "ifc")
    assert refused.value.reason == "resource_limit_exceeded"
    with pytest.raises(ArtifactError):
        store.retain_source(_write(tmp_path / "big.ids", b"12345"), "ids")


def test_tampered_or_missing_retained_source_is_never_replaced(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "a")
    original = _write(tmp_path / "in" / "modelo.ifc", IFC_BYTES)
    retained = store.retain_source(original, "ifc")
    ref = _ref_for(retained.sha256, retained.size_bytes)
    stored = store.source_path(retained.storage_key)

    stored.write_bytes(IFC_BYTES + b"/* alterado */")
    original.write_bytes(IFC_BYTES)
    with pytest.raises(ArtifactError) as tampered:
        store.read_verified_source(ref)
    assert tampered.value.reason == "artifact_integrity_error"
    assert stored.read_bytes() == IFC_BYTES + b"/* alterado */"

    stored.unlink()
    with pytest.raises(ArtifactError) as missing:
        store.read_verified_source(ref)
    assert missing.value.reason == "artifact_unavailable"
    assert not stored.exists()


def test_destination_with_other_bytes_is_collision_not_overwrite(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "a")
    digest = hashlib.sha256(IFC_BYTES).hexdigest()
    squatter = _write(tmp_path / "a" / "s" / "ifc" / digest, b"outros bytes")

    with pytest.raises(ArtifactError) as collision:
        store.retain_source(_write(tmp_path / "in.ifc", IFC_BYTES), "ifc")

    assert collision.value.reason == "storage_collision"
    assert squatter.read_bytes() == b"outros bytes"


@pytest.mark.parametrize(
    "key",
    ["s/ifc/../../x", "../s/ifc/" + "a" * 64, "C:/x", "s/bcf/" + "a" * 64, "s/ifc/" + "A" * 64],
)
def test_storage_keys_are_closed_patterns(tmp_path: Path, key: str) -> None:
    with pytest.raises(ArtifactError) as refused:
        LocalArtifactStore(tmp_path / "a").source_path(key)
    assert refused.value.reason == "unsafe_source"


def _release(tmp_path: Path, version: str = "1.0.0") -> tuple[CatalogReleaseRef, Path]:
    return f.write_synthetic_release(tmp_path / "pkg", f.minimal_content(), version)


def test_retained_catalog_is_a_verified_copy(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "a")
    ref, package = _release(tmp_path)

    retained = store.retain_catalog(ref, package)

    assert isinstance(retained, RetainedCatalogRef)
    assert (retained.catalog, retained.origin) == (ref, "retained_local_package")
    assert retained.content_origin == "synthetic_fixture"
    reader = store.open_retained_catalog(retained)
    assert reader.ref == ref
    assert store.catalog_dir(retained) != package
    assert store.retain_catalog(ref, package).storage_key == retained.storage_key


def test_catalog_package_errors_keep_their_type_and_reason(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "a")
    ref, package = _release(tmp_path)
    wrong = ref.model_copy(update={"manifest_sha256": "0" * 64})
    with pytest.raises(CatalogPackageError) as integrity:
        store.retain_catalog(wrong, package)
    assert integrity.value.reason == "integrity"
    (package / "extra.json").write_text("[]", encoding="utf-8")
    with pytest.raises(CatalogPackageError) as layout:
        store.retain_catalog(ref, package)
    assert layout.value.reason == "layout"
    assert store.inspect_orphans(set()).releases == ()


def test_retained_catalog_tampered_or_missing_is_artifact_error(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "a")
    ref, package = _release(tmp_path)
    retained = store.retain_catalog(ref, package)
    bindings = store.catalog_dir(retained) / "bindings.json"

    bindings.write_bytes(bindings.read_bytes() + b" ")
    with pytest.raises(ArtifactError) as tampered:
        store.open_retained_catalog(retained)
    assert tampered.value.reason == "artifact_integrity_error"
    assert isinstance(tampered.value.__cause__, CatalogPackageError)

    for item in store.catalog_dir(retained).iterdir():
        item.unlink()
    store.catalog_dir(retained).rmdir()
    with pytest.raises(ArtifactError) as missing:
        store.open_retained_catalog(retained)
    assert missing.value.reason == "artifact_unavailable"


def test_inspect_orphans_reports_without_deleting(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "a")
    kept = store.retain_source(_write(tmp_path / "a.ifc", IFC_BYTES), "ifc")
    orphan = store.retain_source(_write(tmp_path / "b.ids", b"<ids/>"), "ids")
    ref, package = _release(tmp_path)
    release = store.retain_catalog(ref, package)
    leftover = tmp_path / "a" / "t" / "resto"
    _write(leftover, b"parcial")

    report = store.inspect_orphans({kept.storage_key})

    assert report.sources == (orphan.storage_key,)
    assert report.releases == (release.storage_key,)
    assert report.staging == ("t/resto",)
    assert store.source_path(orphan.storage_key).exists()
    assert leftover.exists()


def _junction(link: Path, target: Path) -> None:
    """Junction real (Windows); sem permissão do SO o teste é pulado, nunca aprovado."""
    if os.name != "nt":
        pytest.skip("junction é recurso do Windows")
    import _winapi

    target.mkdir(parents=True, exist_ok=True)
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        _winapi.CreateJunction(str(target), str(link))
    except OSError as exc:  # pragma: no cover - depende da política local
        pytest.skip(f"SO negou criar junction ({exc}); proteção NÃO verificada aqui")


def test_staging_area_that_is_a_junction_is_refused_before_writing(tmp_path: Path) -> None:
    """STORE-02: ``t/`` como junction para fora da raiz nunca recebe bytes."""
    store = LocalArtifactStore(tmp_path / "a")
    external = tmp_path / "external"
    _junction(store.root / "t", external)
    source = _write(tmp_path / "in" / "modelo.ifc", IFC_BYTES)
    with pytest.raises(ArtifactError) as refused:
        store.retain_source(source, "ifc")
    assert refused.value.reason == "unsafe_source"
    assert list(external.iterdir()) == []
    with pytest.raises(ArtifactError):
        store.retain_catalog(*_release(tmp_path))
    assert list(external.iterdir()) == []


def test_internal_source_area_junction_is_refused_on_read(tmp_path: Path) -> None:
    """STORE-02: ``s/ifc`` como junction para dentro da raiz não vira arquivo regular."""
    store = LocalArtifactStore(tmp_path / "a")
    digest = hashlib.sha256(IFC_BYTES).hexdigest()
    physical = store.root / "physical"
    _write(physical / digest, IFC_BYTES)
    _junction(store.root / "s" / "ifc", physical)
    with pytest.raises(ArtifactError) as refused:
        store.read_verified_source(_ref_for(digest, len(IFC_BYTES)))
    assert refused.value.reason == "unsafe_source"


def test_publication_areas_that_are_junctions_are_refused(tmp_path: Path) -> None:
    """STORE-02 no adapter E2: preparo ``p/s`` como junction para fora é recusado."""
    from src.artifacts.curation_adapter import LocalReleaseArtifactStore
    from src.domain_catalog.publication import ArtifactStoreError

    store = LocalArtifactStore(tmp_path / "a")
    external = tmp_path / "external"
    _junction(store.publication_root() / "s", external)
    publication = LocalReleaseArtifactStore(store.publication_root())
    release = f.build_synthetic_release(f.minimal_content())
    with pytest.raises(ArtifactStoreError):
        publication.stage("urn:uuid:aaaaaaaa-bbbb-4ccc-8123-000000000001", release)
    assert list(external.iterdir()) == []


@pytest.mark.parametrize(
    ("tag", "is_link"),
    [
        (0xA0000003, True),  # IO_REPARSE_TAG_MOUNT_POINT (junction)
        (0xA000000C, True),  # IO_REPARSE_TAG_SYMLINK
        (0x9000001A, False),  # IO_REPARSE_TAG_CLOUD (OneDrive Files On-Demand)
        (0x80000013, False),  # IO_REPARSE_TAG_DEDUP
        (0, True),  # atributo de reparse sem tag conhecida: recusa conservadora
    ],
)
def test_only_name_surrogate_reparse_points_count_as_links(tag: int, is_link: bool) -> None:
    """M-09: junction/symlink são links; pasta de nuvem/dedup não é recusada como link."""
    import stat
    from types import SimpleNamespace

    from src.artifacts.storage import _is_link

    info = SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400, st_reparse_tag=tag)
    assert _is_link(info) is is_link  # type: ignore[arg-type]
    plain = SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x10, st_reparse_tag=0)
    assert _is_link(plain) is False  # type: ignore[arg-type]
