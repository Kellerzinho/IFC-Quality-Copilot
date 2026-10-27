"""Construção de pacote de release (M1-06); conteúdo SINTÉTICO.

O hash de identidade é o SHA-256 dos bytes do manifesto, guardado fora dele. Os mesmos
dados geram os mesmos bytes; rascunho nunca vira release; pasta existente nunca é
sobrescrita. Publicação com staging, promoção atômica e recibo é a M1-09.
"""

import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.domain_catalog.content import CatalogContent
from src.domain_catalog.errors import CatalogValidationError
from src.domain_catalog.models import LocalizedText
from src.domain_catalog.package import DATA_FILES, CatalogManifest, write_release_dir
from tests.domain_catalog import factories as f


def _reversed(content: CatalogContent) -> CatalogContent:
    return content.model_copy(
        update={kind: tuple(reversed(getattr(content, kind))) for kind in DATA_FILES}
    )


def test_release_bytes_do_not_depend_on_entity_order() -> None:
    base = f.build_synthetic_release()
    reordered = f.build_synthetic_release(_reversed(f.resolution_content()))

    assert reordered.manifest_bytes == base.manifest_bytes
    assert reordered.data == base.data
    assert reordered.ref == base.ref


def test_identity_hash_covers_manifest_bytes_and_lives_outside_them() -> None:
    release = f.build_synthetic_release()

    assert release.ref.manifest_sha256 == hashlib.sha256(release.manifest_bytes).hexdigest()
    assert release.ref.manifest_sha256.encode() not in release.manifest_bytes
    assert (release.ref.catalog_id, release.ref.version) == (f.SYN_CATALOG_ID, "1.0.0")


def test_manifest_lists_every_data_file_with_size_hash_and_entries() -> None:
    release = f.build_synthetic_release()
    listed = {item.path: item for item in release.manifest.files}

    assert set(listed) == set(release.data) == set(DATA_FILES.values())
    for path, data in release.data.items():
        assert listed[path].bytes == len(data)
        assert listed[path].sha256 == hashlib.sha256(data).hexdigest()
    assert listed["bindings.json"].entries == 10
    assert listed["units.json"].entries == 2


def test_label_change_keeps_concept_id_and_changes_release_identity() -> None:
    content = f.resolution_content()
    first = content.concepts[0]
    relabeled = first.model_copy(
        update={"labels": (LocalizedText(lang="pt-BR", text="Rótulo revisado"),)}
    )
    changed = content.model_copy(update={"concepts": (relabeled, *content.concepts[1:])})

    base = f.build_synthetic_release(content)
    other = f.build_synthetic_release(changed)

    assert other.ref.manifest_sha256 != base.ref.manifest_sha256
    assert relabeled.id == first.id


def test_draft_content_cannot_be_packaged() -> None:
    with pytest.raises(CatalogValidationError):
        f.build_synthetic_release(f.minimal_content(lifecycle="draft"))


def test_content_origin_is_declared_in_manifest() -> None:
    assert f.build_synthetic_release().manifest.content_origin == "synthetic_fixture"


@pytest.mark.parametrize("version", [True, 1.0], ids=["booleano", "float"])
def test_manifest_model_accepts_only_the_integer_format_version(version: object) -> None:
    # Revisão E1-09: o modelo também recusa, não só a pré-checagem do reader.
    data = f.build_synthetic_release().manifest.model_dump(mode="json")
    data["format_version"] = version

    with pytest.raises(ValidationError, match="format_version"):
        CatalogManifest.model_validate(data)


def test_accented_names_are_stored_byte_exact() -> None:
    content = f.minimal_content()
    accented = content.bindings[0].model_copy(update={"set_name": "EB_Orçamento"})
    release = f.build_synthetic_release(content.model_copy(update={"bindings": (accented,)}))

    assert "EB_Orçamento".encode() in release.data["bindings.json"]


def test_existing_release_directory_is_never_overwritten(tmp_path: Path) -> None:
    release = f.build_synthetic_release()
    destination = tmp_path / "1.0.0"
    write_release_dir(release, destination)
    before = {p.name: p.read_bytes() for p in destination.iterdir()}

    with pytest.raises(FileExistsError):
        write_release_dir(f.build_synthetic_release(version="1.0.0"), destination)

    assert {p.name: p.read_bytes() for p in destination.iterdir()} == before
