"""Candidato e publicação de release (E2, M1-09).

Conteúdo, catálogo e atores SINTÉTICOS. Os releases "publicados" aqui existem só nas
pastas temporárias do adaptador de teste não operacional, com conteúdo rotulado
``synthetic_fixture``: não são catálogo real nem aprovação de conteúdo da Daiane.
"""

import hashlib
from pathlib import Path

import pytest

from src.domain_catalog.content import CatalogContent
from src.domain_catalog.curation_errors import (
    ActorNotAllowedError,
    CandidateMismatchError,
    CommandValidationError,
    ContentHashMismatchError,
    CurationNotFoundError,
    InvalidTransitionError,
    PublicationGateError,
)
from src.domain_catalog.curation_models import (
    ADOPTION_STATEMENT,
    IDENTITY_STATEMENT,
    CommandMeta,
    CommandOutcome,
    DeprecateEntity,
    DraftHead,
    DraftPatch,
    PublicationReceipt,
    ReleaseCandidate,
    RemoveProposal,
    UpsertEntity,
)
from src.domain_catalog.models import ReconciliationDecision
from src.domain_catalog.package import ComponentTerms
from src.domain_catalog.reader import open_catalog
from tests.domain_catalog import factories as f
from tests.domain_catalog.curation_adapters import CurationEnv, make_env

TERMS = (ComponentTerms(component="conteúdo", terms="sintético, sem terceiros"),)
CONCEPT_2 = "urn:uuid:00000000-0000-4000-8000-0000000d3001"


@pytest.fixture
def env(tmp_path: Path) -> CurationEnv:
    return make_env(tmp_path)


def _meta(command_id: str, actor: str) -> CommandMeta:
    return CommandMeta(command_id=command_id, actor_context_id=actor)


def _approved(env: CurationEnv, tag: str = "1", head: DraftHead | None = None) -> DraftHead:
    """Rascunho sintético submetido e aprovado pelo curador sintético."""
    if head is None:
        head = env.curation.import_draft(
            _meta(f"cmd-imp-{tag}", env.importer),
            title="Proposta sintética",
            catalog=f.catalog_identity(),
            content=f.minimal_content("draft"),
            source_label="fixture sintética",
            reason="propostas sintéticas",
        ).value
    submitted = env.curation.submit_for_review(
        _meta(f"cmd-sub-{tag}", env.curator),
        draft_id=head.draft.draft_id,
        revision=head.revision,
        content_sha256=head.content_sha256,
        reason="pronto",
    ).value
    env.curation.review_draft(
        _meta(f"cmd-apr-{tag}", env.curator),
        draft_id=head.draft.draft_id,
        revision=submitted.revision,
        content_sha256=submitted.content_sha256,
        verdict="approve",
        justification="Conteúdo sintético conferido para o teste.",
    )
    return env.curation.get_head(head.draft.draft_id)


def _prepare(
    env: CurationEnv, head: DraftHead, version: str = "1.0.0", tag: str = "1"
) -> ReleaseCandidate:
    return env.publication.prepare_release(
        _meta(f"cmd-prp-{tag}", env.curator),
        draft_id=head.draft.draft_id,
        revision=head.revision,
        content_sha256=head.content_sha256,
        version=version,
        terms=TERMS,
        reason="preparar release sintético",
    ).value


def _publish(
    env: CurationEnv, candidate: ReleaseCandidate, tag: str = "1", actor: str | None = None
) -> CommandOutcome[PublicationReceipt]:
    return env.publication.publish(
        _meta(f"cmd-pub-{tag}", actor or env.curator),
        candidate_id=candidate.candidate_id,
        version=candidate.release.version,
        manifest_sha256=candidate.release.manifest_sha256,
        justification="Publicação sintética de teste.",
    )


def _tree_hashes(path: Path) -> dict[str, str]:
    return {
        item.name: hashlib.sha256(item.read_bytes()).hexdigest() for item in sorted(path.iterdir())
    }


# --- candidato --------------------------------------------------------------------------


def test_candidate_requires_an_approved_draft(env: CurationEnv) -> None:
    head = env.curation.import_draft(
        _meta("cmd-imp-x", env.importer),
        title="Sem aprovação",
        catalog=f.catalog_identity(),
        content=f.minimal_content("draft"),
        source_label="fixture",
        reason="teste",
    ).value

    with pytest.raises(InvalidTransitionError, match="aprovad"):
        _prepare(env, head)

    assert env.artifacts.staged_dirs() == ()


def test_candidate_is_staged_isolated_and_reopened_by_its_exact_identity(
    env: CurationEnv,
) -> None:
    head = _approved(env)

    candidate = _prepare(env, head)

    staged = env.artifacts.staged_path(candidate.candidate_id)
    assert staged is not None
    manifest_bytes = (staged / "manifest.json").read_bytes()
    assert hashlib.sha256(manifest_bytes).hexdigest() == candidate.release.manifest_sha256
    reader = open_catalog(candidate.release, staged)
    assert {c.lifecycle for c in reader.content.concepts} == {"approved"}
    assert candidate.state == "prepared"
    assert (candidate.revision, candidate.content_sha256) == (head.revision, head.content_sha256)
    assert candidate.content_origin == "synthetic_fixture"
    assert candidate.previous_release is None
    assert f"concepts:{f.CONCEPT_ID}" in candidate.diff.added
    assert env.publication.latest_published(f.SYN_CATALOG_ID) is None


def test_assistant_cannot_prepare_a_candidate(env: CurationEnv) -> None:
    head = _approved(env)

    with pytest.raises(ActorNotAllowedError):
        env.publication.prepare_release(
            _meta("cmd-prp-x", env.assistant),
            draft_id=head.draft.draft_id,
            revision=head.revision,
            content_sha256=head.content_sha256,
            version="1.0.0",
            terms=TERMS,
            reason="assistente",
        )


def test_candidate_for_another_content_hash_is_refused(env: CurationEnv) -> None:
    head = _approved(env)

    with pytest.raises(ContentHashMismatchError):
        env.publication.prepare_release(
            _meta("cmd-prp-x", env.curator),
            draft_id=head.draft.draft_id,
            revision=head.revision,
            content_sha256="a" * 64,
            version="1.0.0",
            terms=TERMS,
            reason="hash errado",
        )
    assert env.artifacts.staged_dirs() == ()


# --- publicação -------------------------------------------------------------------------


def test_publication_records_receipt_with_declared_responsibles(env: CurationEnv) -> None:
    candidate = _prepare(env, _approved(env))

    outcome = _publish(env, candidate)
    receipt = outcome.value

    assert receipt.release == candidate.release
    assert receipt.approved_by.declared_name == "Pessoa Curadora Sintética"
    assert receipt.approval_justification == "Conteúdo sintético conferido para o teste."
    assert receipt.published_by.declared_name == "Pessoa Curadora Sintética"
    assert receipt.publication_justification == "Publicação sintética de teste."
    assert receipt.identity_assurance == "unverified_local"
    assert receipt.identity_statement == IDENTITY_STATEMENT
    assert (receipt.store_operational, receipt.artifact_store_operational) == (False, False)
    assert receipt.content_origin == "synthetic_fixture"
    assert outcome.receipt.store_operational is False
    assert env.publication.latest_published(f.SYN_CATALOG_ID) == candidate.release
    assert env.curation.get_draft(candidate.draft_id).state == "published"


def test_published_release_reopens_by_exact_reference(env: CurationEnv) -> None:
    candidate = _prepare(env, _approved(env))
    _publish(env, candidate)

    reader = env.publication.open_published(candidate.release)

    assert reader.ref == candidate.release
    assert env.artifacts.staged_path(candidate.candidate_id) is None


@pytest.mark.parametrize(
    ("version", "digest"), [("1.0.1", None), (None, "b" * 64), ("2.0.0", "c" * 64)]
)
def test_publication_needs_the_exact_candidate_version_and_hash(
    env: CurationEnv, version: str | None, digest: str | None
) -> None:
    candidate = _prepare(env, _approved(env))

    with pytest.raises(CandidateMismatchError):
        env.publication.publish(
            _meta("cmd-pub-x", env.curator),
            candidate_id=candidate.candidate_id,
            version=version or candidate.release.version,
            manifest_sha256=digest or candidate.release.manifest_sha256,
            justification="tentativa com identidade errada",
        )

    assert env.publication.get_candidate(candidate.candidate_id).state == "prepared"
    assert env.publication.latest_published(f.SYN_CATALOG_ID) is None
    assert env.artifacts.release_dirs() == ()


@pytest.mark.parametrize("who", ["assistant", "service", "anonymous"])
def test_only_a_person_with_declared_name_publishes(env: CurationEnv, who: str) -> None:
    candidate = _prepare(env, _approved(env))
    actor = {
        "assistant": env.assistant,
        "service": env.importer,
        "anonymous": env.actors.register("human", None),
    }[who]

    with pytest.raises(ActorNotAllowedError):
        _publish(env, candidate, actor=actor)

    assert env.artifacts.release_dirs() == ()


def test_edit_after_preparation_invalidates_candidate_and_blocks_publication(
    env: CurationEnv,
) -> None:
    head = _approved(env)
    candidate = _prepare(env, head)
    concept = f._concept_for(CONCEPT_2, "SYN_TARDIO", lifecycle="draft").model_dump(mode="json")
    env.curation.edit_draft(
        _meta("cmd-edt-1", env.curator),
        draft_id=head.draft.draft_id,
        expected_revision=head.revision,
        patch=DraftPatch(
            operations=(UpsertEntity(op="upsert", kind="concepts", entity=concept),),
            reason="mudança depois do candidato",
        ),
    )

    with pytest.raises(InvalidTransitionError, match="invalidated"):
        _publish(env, candidate)

    assert env.publication.get_candidate(candidate.candidate_id).state == "invalidated"
    assert env.artifacts.release_dirs() == ()


def test_repeated_publish_command_returns_the_same_receipt(env: CurationEnv) -> None:
    candidate = _prepare(env, _approved(env))
    first = _publish(env, candidate)

    again = _publish(env, candidate)

    assert again.replayed is True
    assert again.value == first.value
    assert len(env.artifacts.release_dirs()) == 1


def test_published_candidate_cannot_be_published_again(env: CurationEnv) -> None:
    candidate = _prepare(env, _approved(env))
    _publish(env, candidate)

    with pytest.raises(InvalidTransitionError):
        _publish(env, candidate, tag="2")


def test_unpublished_candidate_is_not_an_available_release(env: CurationEnv) -> None:
    candidate = _prepare(env, _approved(env))

    with pytest.raises(CurationNotFoundError):
        env.publication.open_published(candidate.release)


# --- sequência de releases ---------------------------------------------------------------


def _second_draft(env: CurationEnv, tag: str, code: str = "SYN_SEGUNDO") -> DraftHead:
    base = env.publication.latest_published(f.SYN_CATALOG_ID)
    head = env.curation.create_draft(
        _meta(f"cmd-new-{tag}", env.curator),
        title=f"Evolução {tag}",
        base_release=base,
        reason="nova versão",
    ).value
    concept = f._concept_for(CONCEPT_2, code, lifecycle="draft").model_dump(mode="json")
    return env.curation.edit_draft(
        _meta(f"cmd-edt-{tag}", env.curator),
        draft_id=head.draft.draft_id,
        expected_revision=1,
        patch=DraftPatch(
            operations=(UpsertEntity(op="upsert", kind="concepts", entity=concept),),
            reason="acrescentar conceito",
        ),
    ).value


def test_new_release_preserves_the_previous_one_byte_for_byte(env: CurationEnv) -> None:
    first = _prepare(env, _approved(env))
    _publish(env, first)
    first_dir = env.artifacts.release_path(first.release)
    before = _tree_hashes(first_dir)

    second = _prepare(env, _approved(env, "2", _second_draft(env, "2")), "1.1.0", "2")
    receipt = _publish(env, second, "2").value

    assert receipt.previous_release == first.release
    assert env.publication.latest_published(f.SYN_CATALOG_ID) == second.release
    assert _tree_hashes(first_dir) == before
    assert env.publication.open_published(first.release).content.concepts[0].code == "SYN_METODO"
    assert [p.release for p in env.publication.list_published(f.SYN_CATALOG_ID)] == [
        first.release,
        second.release,
    ]


def test_publication_does_not_adopt_the_release_in_any_project(env: CurationEnv) -> None:
    candidate = _prepare(env, _approved(env))

    receipt = _publish(env, candidate).value

    assert receipt.adoption == "explicit_per_project"
    assert receipt.adoption_statement == ADOPTION_STATEMENT


def test_version_must_grow_from_the_previous_release(env: CurationEnv) -> None:
    first = _prepare(env, _approved(env))
    _publish(env, first)
    head = _approved(env, "2", _second_draft(env, "2"))

    for version in ("1.0.0", "0.9.0"):
        with pytest.raises(PublicationGateError, match="versão"):
            _prepare(env, head, version, f"2-{version}")


def test_candidate_on_a_stale_base_cannot_be_published(env: CurationEnv) -> None:
    first = _prepare(env, _approved(env))
    _publish(env, first)
    late = _approved(env, "3", _second_draft(env, "3", "SYN_TARDIO"))
    early = _prepare(env, _approved(env, "2", _second_draft(env, "2")), "1.1.0", "2")
    late_candidate = _prepare(env, late, "1.2.0", "3")
    _publish(env, early, "2")

    with pytest.raises(PublicationGateError, match="desatualizad"):
        _publish(env, late_candidate, "3")

    assert env.publication.latest_published(f.SYN_CATALOG_ID) == early.release


def test_first_draft_cannot_ignore_an_existing_release(env: CurationEnv) -> None:
    candidate = _prepare(env, _approved(env))
    _publish(env, candidate)

    with pytest.raises(CommandValidationError, match="já tem release publicado"):
        env.curation.create_draft(
            _meta("cmd-new-x", env.curator),
            title="Ignora o histórico",
            catalog=f.catalog_identity(),
            reason="teste",
        )


def test_draft_from_release_starts_with_the_published_content(env: CurationEnv) -> None:
    candidate = _prepare(env, _approved(env))
    _publish(env, candidate)

    head = env.curation.create_draft(
        _meta("cmd-new-y", env.curator),
        title="Evolução",
        base_release=candidate.release,
        reason="nova versão",
    ).value

    revision = env.curation.get_revision(head.draft.draft_id, 1)
    published = env.publication.open_published(candidate.release).content
    assert revision.origin == "base_release"
    assert revision.content == published
    assert isinstance(revision.content, CatalogContent)
    report = env.curation.validate_draft(head.draft.draft_id)
    assert "draft.no_changes" in {x.code for x in report.by_severity("warning")}


# --- pendências reconhecidas ---------------------------------------------------------------

DECISION_ID = "urn:uuid:00000000-0000-4000-8000-0000000d3002"


def _candidate_with_pending_decision(env: CurationEnv) -> ReleaseCandidate:
    """Candidato sintético com uma decisão de reconciliação pendente (sem uso afetado)."""
    decision = ReconciliationDecision(
        id=DECISION_ID,
        code="syn-divergencia-aberta",
        status="pending",
        source_assertion_ids=(f.SYN_ASSERTION_ID,),
        summary="Divergência sintética ainda aberta.",
    )
    content = f.minimal_content("draft").model_copy(
        update={"reconciliation_decisions": (decision,)}
    )
    head = env.curation.import_draft(
        _meta("cmd-imp-pend", env.importer),
        title="Proposta com pendência",
        catalog=f.catalog_identity(),
        content=content,
        source_label="fixture sintética",
        reason="pendência visível",
    ).value
    return _prepare(env, _approved(env, "pend", head), tag="pend")


def test_acknowledging_other_items_than_the_candidate_pending_is_refused(
    env: CurationEnv,
) -> None:
    candidate = _candidate_with_pending_decision(env)
    assert [p.entity_id for p in candidate.pending_items] == [DECISION_ID]

    with pytest.raises(PublicationGateError, match="reconhecimento"):
        env.publication.publish(
            _meta("cmd-pub-ack-1", env.curator),
            candidate_id=candidate.candidate_id,
            version=candidate.release.version,
            manifest_sha256=candidate.release.manifest_sha256,
            justification="reconhecendo a pendência errada",
            acknowledged_pending=("urn:uuid:00000000-0000-4000-8000-00000000ffff",),
        )

    assert env.publication.get_candidate(candidate.candidate_id).state == "prepared"


def test_exact_acknowledgement_is_recorded_in_the_receipt(env: CurationEnv) -> None:
    candidate = _candidate_with_pending_decision(env)

    receipt = env.publication.publish(
        _meta("cmd-pub-ack-2", env.curator),
        candidate_id=candidate.candidate_id,
        version=candidate.release.version,
        manifest_sha256=candidate.release.manifest_sha256,
        justification="publicar com a divergência explícita",
        acknowledged_pending=(DECISION_ID,),
    ).value

    assert receipt.acknowledged_pending == (DECISION_ID,)
    assert [p.entity_id for p in receipt.pending_items] == [DECISION_ID]
    published = env.publication.open_published(candidate.release)
    assert published.content.reconciliation_decisions[0].status == "pending"


def test_new_draft_cannot_start_from_a_superseded_release(env: CurationEnv) -> None:
    first = _prepare(env, _approved(env))
    _publish(env, first)
    second = _prepare(env, _approved(env, "2", _second_draft(env, "2")), "1.1.0", "2")
    _publish(env, second, "2")

    with pytest.raises(CommandValidationError, match="não é o último publicado"):
        env.curation.create_draft(
            _meta("cmd-new-velho", env.curator),
            title="Parte de release antigo",
            base_release=first.release,
            reason="tentativa de reabrir histórico",
        )

    assert all(
        d.base_release != first.release or d.state == "published"
        for d in env.curation.list_drafts()
    )


def test_withdrawn_reproposal_of_an_inherited_concept_allows_publishing_its_deprecation(
    env: CurationEnv,
) -> None:
    """Achado E2-04: retirar a proposta sobre entidade herdada é caminho suportado."""
    first = _prepare(env, _approved(env))
    _publish(env, first)
    published = env.publication.open_published(first.release).content.concepts[0]
    head = env.curation.create_draft(
        _meta("cmd-new-dep", env.curator),
        title="Depreciação",
        base_release=first.release,
        reason="depreciar conceito",
    ).value
    head = env.curation.edit_draft(
        _meta("cmd-edt-dep-1", env.curator),
        draft_id=head.draft.draft_id,
        expected_revision=head.revision,
        patch=DraftPatch(
            operations=(
                UpsertEntity(
                    op="upsert",
                    kind="concepts",
                    entity={**published.model_dump(mode="json"), "lifecycle": "draft"},
                ),
            ),
            reason="repropor sem mudança de dados",
        ),
    ).value
    assert _approved(env, "dep", head).draft.state == "approved"

    head = env.curation.edit_draft(
        _meta("cmd-edt-dep-2", env.curator),
        draft_id=head.draft.draft_id,
        expected_revision=head.revision,
        patch=DraftPatch(
            operations=(
                RemoveProposal(op="remove", kind="concepts", entity_id=f.CONCEPT_ID),
                DeprecateEntity(op="deprecate", kind="concepts", entity_id=f.CONCEPT_ID),
            ),
            reason="retirar a proposta e depreciar",
        ),
    ).value

    assert (head.draft.state, head.draft.approval_id) == ("editing", None)
    assert env.curation.get_revision(head.draft.draft_id, head.revision).operations == (
        f"restore concepts {f.CONCEPT_ID}",
        f"deprecate concepts {f.CONCEPT_ID}",
    )
    second = _prepare(env, _approved(env, "dep2", head), "1.1.0", "dep2")
    assert second.diff.deprecated == (f"concepts:{f.CONCEPT_ID}",)
    _publish(env, second, "dep2")
    released = env.publication.open_published(second.release).content.concepts[0]
    assert released.lifecycle == "deprecated"
    assert released.model_dump(exclude={"lifecycle"}) == published.model_dump(exclude={"lifecycle"})
    assert env.publication.open_published(first.release).content.concepts[0] == published
