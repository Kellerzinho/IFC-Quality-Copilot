"""Pin de catálogo e proveniência obtida pelo serviço a partir da cadeia E2 real (§3.2)."""

import uuid
from pathlib import Path

import pytest
from pydantic import ValidationError

pytest.importorskip("ifctester", reason="extra e3 não instalado (ifctester==0.8.5)")

from src.domain_catalog.actor import ActorSnapshot
from src.domain_catalog.contracts import CatalogReleaseRef
from src.domain_catalog.migration import resolve_provenance
from src.domain_catalog.models import SourceArtifact
from src.domain_catalog.provenance import CatalogProvenance
from src.operations.contracts import canonical_sha256
from src.operations.project_models import ProjectCatalogPin
from tests.domain_catalog import factories as f
from tests.operations.adoption_env import apply, make_adoption_env, prepare
from tests.operations.e3_env import make_real_env, publish_first

REF = CatalogReleaseRef(catalog_id=f.SYN_CATALOG_ID, version="1.0.0", manifest_sha256="a" * 64)
CHAIN = {
    "receipt_id": "urn:uuid:00000000-0000-4000-8000-00000000a001",
    "receipt_sha256": "b" * 64,
    "candidate_id": "urn:uuid:00000000-0000-4000-8000-00000000a002",
    "intent_id": "urn:uuid:00000000-0000-4000-8000-00000000a003",
    "draft_id": "urn:uuid:00000000-0000-4000-8000-00000000a004",
    "revision": 2,
    "content_sha256": "c" * 64,
    "approval_id": "urn:uuid:00000000-0000-4000-8000-00000000a005",
}


def _provenance(**changes: object) -> CatalogProvenance:
    data: dict[str, object] = {
        "state": "synthetic_test_published",
        "catalog": REF,
        "content_origin": "synthetic_fixture",
        "store_purpose": "synthetic_test",
        **CHAIN,
    }
    data.update(changes)
    return CatalogProvenance.model_validate(data)


def _human(kind: str = "human") -> ActorSnapshot:
    return ActorSnapshot(
        actor_context_id=str(uuid.uuid4()),
        installation_id="inst",
        session_id="sess",
        actor_kind=kind,  # type: ignore[arg-type]
        declared_name="Pessoa Sintética Declarada (teste)",
        identity_assurance="unverified_local",
        registered_at_utc="2026-10-22T00:00:00Z",
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"state": "unverified_package"},
        {"state": "published_local"},
        {"store_purpose": "operational"},
        {"receipt_id": None},
        {"revision": 0},
    ],
)
def test_provenance_chain_and_labels_are_coherent(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _provenance(**changes)
    assert _provenance().published
    unverified = CatalogProvenance(
        state="unverified_package",
        catalog=REF,
        content_origin="curated",
        store_purpose="operational",
    )
    assert not unverified.published


def test_pin_requires_published_provenance_human_actor_and_contiguous_revision() -> None:
    base: dict[str, object] = {
        "project_id": uuid.uuid4(),
        "pin_revision": 1,
        "catalog": REF,
        "catalog_provenance": _provenance(),
        "adoption_id": uuid.uuid4(),
        "previous_pin_revision": None,
        "actor_snapshot": _human(),
        "reason": "adoção sintética",
        "created_at_utc": "2026-10-22T00:00:00Z",
    }
    assert ProjectCatalogPin.model_validate(base).pin_revision == 1
    unverified = CatalogProvenance(
        state="unverified_package",
        catalog=REF,
        content_origin="synthetic_fixture",
        store_purpose="synthetic_test",
    )
    for bad in (
        {"catalog_provenance": unverified},
        {"actor_snapshot": _human("assistant")},
        {"pin_revision": 2, "previous_pin_revision": None},
        {"pin_revision": 3, "previous_pin_revision": 1},
        {"catalog": REF.model_copy(update={"version": "2.0.0"})},
    ):
        with pytest.raises(ValidationError):
            ProjectCatalogPin.model_validate({**base, **bad})


def test_resolved_provenance_cites_the_exact_historical_chain(tmp_path: Path) -> None:
    env = make_real_env(tmp_path)
    receipt = publish_first(env, f.minimal_content("draft"))
    with env.store.transaction() as uow:
        provenance = resolve_provenance(uow, receipt.release, "synthetic_fixture")
        stored = uow.curation.get("publication", f"{receipt.release.catalog_id}#1.0.0")
    assert stored is not None
    assert provenance.state == "synthetic_test_published"
    assert (provenance.receipt_id, provenance.candidate_id, provenance.intent_id) == (
        receipt.receipt_id,
        receipt.candidate_id,
        receipt.intent_id,
    )
    assert provenance.receipt_sha256 == canonical_sha256(stored.document)
    assert (provenance.draft_id, provenance.revision, provenance.approval_id) == (
        receipt.draft_id,
        receipt.revision,
        receipt.approval_id,
    )


def test_loose_receipt_without_chain_stays_unverified(tmp_path: Path) -> None:
    env = make_real_env(tmp_path / "a")
    receipt = publish_first(env, f.minimal_content("draft"))
    other = make_real_env(tmp_path / "b")
    with other.store.transaction() as uow:
        uow.curation.insert(
            "publication", f"{receipt.release.catalog_id}#1.0.0", receipt.model_dump(mode="json")
        )
        provenance = resolve_provenance(uow, receipt.release, "synthetic_fixture")
    assert provenance.state == "unverified_package"
    assert provenance.receipt_id is None


def test_curated_test_package_published_in_operational_store_is_published_local(
    tmp_path: Path,
) -> None:
    """Conteúdo de TESTE rotulado ``curated`` só para exercitar o ramo; não é fonte real."""
    aenv = make_adoption_env(tmp_path, purpose="operational")
    labeled = f.minimal_content("draft").model_copy(
        update={
            "source_artifacts": (
                SourceArtifact(
                    id=f.SYN_SOURCE_ID,
                    title="Fonte de teste rotulada curated (não real)",
                    artifact_type="research_matrix",
                    terms="teste automatizado, sem conteúdo de terceiros",
                ),
            )
        }
    )
    receipt = publish_first(aenv.env, labeled)
    assert receipt.content_origin == "curated"
    plan = prepare(aenv, receipt.release, "initial")
    assert plan.target_provenance.state == "published_local"
    assert apply(aenv, plan).status == "applied"
