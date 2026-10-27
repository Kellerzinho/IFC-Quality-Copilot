"""Porta E2 de artefatos de release real e publicação sintética com adaptadores reais."""

from pathlib import Path

import pytest

from src.artifacts.curation_adapter import LocalReleaseArtifactStore
from src.domain_catalog.curation_models import PublicationReceipt
from src.domain_catalog.publication import ArtifactStoreError, ReleaseCollisionError
from tests.domain_catalog import factories as f
from tests.operations.e3_env import make_real_env, publish_first

CANDIDATE = "urn:uuid:00000000-0000-4000-8000-00000000c001"


def test_stage_is_exclusive_and_promotion_never_overwrites(tmp_path: Path) -> None:
    store = LocalReleaseArtifactStore(tmp_path / "p")
    release = f.build_synthetic_release(f.minimal_content())
    staged = store.stage(CANDIDATE, release)
    assert sorted(p.name for p in staged.iterdir()) == sorted(["manifest.json", *release.data])
    with pytest.raises(ArtifactStoreError) as again:
        store.stage(CANDIDATE, release)
    assert again.value.phase == "stage"

    final = store.release_path(release.ref)
    final.mkdir(parents=True)
    (final / "sentinela").write_text("ocupado", encoding="utf-8")
    with pytest.raises(ReleaseCollisionError):
        store.promote(CANDIDATE, release.ref)
    assert (final / "sentinela").read_text(encoding="utf-8") == "ocupado"
    assert staged.is_dir()


def test_quarantine_moves_without_deleting_and_inventory_sees_loose_entries(
    tmp_path: Path,
) -> None:
    store = LocalReleaseArtifactStore(tmp_path / "p")
    release = f.build_synthetic_release(f.minimal_content())
    staged = store.stage(CANDIDATE, release)
    promoted = store.promote(CANDIDATE, release.ref)
    assert not staged.exists()
    assert store.inventory().releases == (promoted,)

    moved = store.quarantine(promoted, "sem-recibo")
    assert not promoted.exists()
    assert (moved / "manifest.json").read_bytes() == release.manifest_bytes
    assert store.operational is True


def test_e2_publication_with_real_adapters_records_durable_receipt(tmp_path: Path) -> None:
    env = make_real_env(tmp_path)

    receipt = publish_first(env, f.minimal_content("draft"))

    assert isinstance(receipt, PublicationReceipt)
    assert receipt.content_origin == "synthetic_fixture"
    assert (receipt.store_operational, receipt.artifact_store_operational) == (True, True)
    reopened = make_real_env(tmp_path)
    assert reopened.publication.list_published(f.SYN_CATALOG_ID) == (receipt,)
    reader = reopened.publication.open_published(receipt.release)
    assert reader.describe().content_origin == "synthetic_fixture"
    inspection = reopened.publication.inspect()
    assert (inspection.pending_intents, inspection.unregistered_releases) == ((), ())
    with reopened.store.transaction() as uow:
        curation_events = uow.events.list(namespace="curation")
        commands = [uow.commands.get(e[1]["command_id"]) for e in curation_events]
    assert curation_events
    assert all(row is not None and row.namespace == "curation" for row in commands)


def test_distinct_uuids_with_the_same_suffix_never_share_a_folder(tmp_path: Path) -> None:
    """E3-14: UUIDv1 distintos com os mesmos dois últimos grupos têm pastas distintas."""
    from src.artifacts.curation_adapter import LocalReleaseArtifactStore
    from src.domain_catalog.contracts import CatalogReleaseRef
    from tests.domain_catalog import factories as fac

    first = "urn:uuid:aaaaaaaa-bbbb-1ccc-8123-000000000001"
    second = "urn:uuid:dddddddd-eeee-1fff-8123-000000000001"
    store = LocalReleaseArtifactStore(tmp_path / "p")
    refs = [
        CatalogReleaseRef(catalog_id=catalog_id, version="1.0.0", manifest_sha256=digest)
        for catalog_id, digest in ((first, "a" * 64), (second, "b" * 64))
    ]
    assert store.release_path(refs[0]) != store.release_path(refs[1])
    assert store.staging_path(first) != store.staging_path(second)

    release = fac.build_synthetic_release(fac.minimal_content())
    staged = [store.stage(candidate, release) for candidate in (first, second)]
    assert staged[0] != staged[1]
    assert all(path.is_dir() for path in staged)
