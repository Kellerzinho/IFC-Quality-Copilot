"""Revisão humana e aprovação de uma revisão exata do rascunho (E2, M1-08).

Atores e conteúdo SINTÉTICOS, no adaptador de teste não operacional. Nada aqui é
aprovação real de conteúdo: o "curador" é um contexto sintético. Verifica que a
aprovação se liga ao número e ao hash da revisão, que qualquer edição posterior a
invalida, que só pessoa com responsável declarado aprova e que validação com erro
bloqueia submissão e aprovação.
"""

from pathlib import Path

import pytest

from src.domain_catalog.content import CatalogContent
from src.domain_catalog.curation_errors import (
    ActorNotAllowedError,
    CommandValidationError,
    ContentHashMismatchError,
    InvalidTransitionError,
    RevisionConflictError,
    ValidationGateError,
)
from src.domain_catalog.curation_models import (
    CommandMeta,
    CommandOutcome,
    DraftHead,
    DraftPatch,
    RequestedField,
    ReviewRecord,
    UpsertEntity,
)
from src.domain_catalog.models import IFCBinding
from tests.domain_catalog import factories as f
from tests.domain_catalog.curation_adapters import CurationEnv, make_env
from tests.domain_catalog.factories import R

CONCEPT_2 = "urn:uuid:00000000-0000-4000-8000-0000000d2001"


@pytest.fixture
def env(tmp_path: Path) -> CurationEnv:
    return make_env(tmp_path)


def _meta(command_id: str, actor: str) -> CommandMeta:
    return CommandMeta(command_id=command_id, actor_context_id=actor)


def _draft_with_request(env: CurationEnv, content: CatalogContent | None = None) -> DraftHead:
    request = env.curation.request_change(
        _meta("cmd-req-0001", env.operator),
        catalog_id=f.SYN_CATALOG_ID,
        motivation="Campo sintético sem cadastro.",
        field=RequestedField(field_name="SYN_Metodo"),
    ).value
    return env.curation.import_draft(
        _meta("cmd-imp-0001", env.importer),
        title="Proposta sintética",
        catalog=f.catalog_identity(),
        content=content if content is not None else f.minimal_content("draft"),
        source_label="fixture sintética",
        reason="propostas sintéticas",
        request_ids=(request.request_id,),
    ).value


def _submit(env: CurationEnv, head: DraftHead, command_id: str = "cmd-sub-0001") -> DraftHead:
    return env.curation.submit_for_review(
        _meta(command_id, env.curator),
        draft_id=head.draft.draft_id,
        revision=head.revision,
        content_sha256=head.content_sha256,
        reason="pronto para revisão",
    ).value


def _approve(
    env: CurationEnv, head: DraftHead, actor: str | None = None, command_id: str = "cmd-apr-0001"
) -> CommandOutcome[ReviewRecord]:
    return env.curation.review_draft(
        _meta(command_id, actor or env.curator),
        draft_id=head.draft.draft_id,
        revision=head.revision,
        content_sha256=head.content_sha256,
        verdict="approve",
        justification="Conteúdo sintético conferido para o teste.",
    )


def _edit(env: CurationEnv, head: DraftHead, command_id: str = "cmd-edt-0001") -> DraftHead:
    concept = f._concept_for(CONCEPT_2, "SYN_SEGUNDO", lifecycle="draft").model_dump(mode="json")
    return env.curation.edit_draft(
        _meta(command_id, env.curator),
        draft_id=head.draft.draft_id,
        expected_revision=head.revision,
        patch=DraftPatch(
            operations=(UpsertEntity(op="upsert", kind="concepts", entity=concept),),
            reason="nova proposta depois da aprovação",
        ),
    ).value


def _request_state(env: CurationEnv) -> str:
    (request,) = env.curation.list_requests()
    return request.state


def test_submission_moves_draft_and_its_request_to_review(env: CurationEnv) -> None:
    head = _draft_with_request(env)

    submitted = _submit(env, head)

    assert submitted.draft.state == "in_review"
    assert _request_state(env) == "in_review"


def test_submission_with_validation_errors_is_refused_without_effect(env: CurationEnv) -> None:
    orphan = f.binding("draft").model_copy(
        update={"concept_id": "urn:uuid:00000000-0000-4000-8000-00000000beef"}
    )
    content = f.minimal_content("draft").model_copy(update={"bindings": (orphan,)})
    head = _draft_with_request(env, content)
    events_before = env.curation.events()

    with pytest.raises(ValidationGateError, match=r"content\.orphan_reference"):
        _submit(env, head)

    assert env.curation.get_draft(head.draft.draft_id).state == "editing"
    assert env.curation.events() == events_before


def test_assistant_cannot_submit_for_review(env: CurationEnv) -> None:
    head = _draft_with_request(env)

    with pytest.raises(ActorNotAllowedError):
        env.curation.submit_for_review(
            _meta("cmd-sub-0002", env.assistant),
            draft_id=head.draft.draft_id,
            revision=head.revision,
            content_sha256=head.content_sha256,
            reason="assistente tentando promover",
        )


def test_submission_with_another_hash_is_refused(env: CurationEnv) -> None:
    head = _draft_with_request(env)

    with pytest.raises(ContentHashMismatchError):
        env.curation.submit_for_review(
            _meta("cmd-sub-0003", env.curator),
            draft_id=head.draft.draft_id,
            revision=head.revision,
            content_sha256="0" * 64,
            reason="hash errado",
        )


def test_approval_binds_the_exact_revision_and_hash(env: CurationEnv) -> None:
    head = _submit(env, _draft_with_request(env))

    outcome = _approve(env, head)
    review = outcome.value
    draft = env.curation.get_draft(head.draft.draft_id)

    assert (review.verdict, review.revision, review.content_sha256) == (
        "approve",
        head.revision,
        head.content_sha256,
    )
    assert review.reviewer.declared_name == "Pessoa Curadora Sintética"
    assert review.reviewer.identity_assurance == "unverified_local"
    assert review.validation.errors == 0
    assert (draft.state, draft.approval_id) == ("approved", review.review_id)
    assert _request_state(env) == "approved"


@pytest.mark.parametrize("who", ["assistant", "anonymous", "service"])
def test_only_a_person_with_declared_name_approves(env: CurationEnv, who: str) -> None:
    head = _submit(env, _draft_with_request(env))
    actor = {
        "assistant": env.assistant,
        "service": env.importer,
        "anonymous": env.actors.register("human", None),
    }[who]

    with pytest.raises(ActorNotAllowedError):
        _approve(env, head, actor=actor)

    assert env.curation.get_draft(head.draft.draft_id).state == "in_review"


def test_approval_of_another_content_hash_is_refused(env: CurationEnv) -> None:
    head = _submit(env, _draft_with_request(env))

    with pytest.raises(ContentHashMismatchError):
        env.curation.review_draft(
            _meta("cmd-apr-0002", env.curator),
            draft_id=head.draft.draft_id,
            revision=head.revision,
            content_sha256="f" * 64,
            verdict="approve",
            justification="hash de outro conteúdo",
        )

    assert env.curation.get_draft(head.draft.draft_id).approval_id is None


def test_edit_after_approval_invalidates_it_and_returns_the_request(env: CurationEnv) -> None:
    head = _submit(env, _draft_with_request(env))
    review = _approve(env, head).value

    edited = _edit(env, env.curation.get_head(head.draft.draft_id))

    draft = env.curation.get_draft(head.draft.draft_id)
    assert (draft.state, draft.approval_id, edited.revision) == ("editing", None, 2)
    assert _request_state(env) == "in_triage"
    invalidated = [
        e
        for e in env.curation.events()
        if e.subject_kind == "review" and e.to_state == "invalidated"
    ]
    assert [(e.subject_id, e.revision) for e in invalidated] == [(review.review_id, 1)]
    assert env.curation.list_reviews(head.draft.draft_id) == (review,)


def test_the_new_revision_needs_its_own_submission_and_approval(env: CurationEnv) -> None:
    head = _submit(env, _draft_with_request(env))
    _approve(env, head)
    edited = _edit(env, env.curation.get_head(head.draft.draft_id))

    with pytest.raises(InvalidTransitionError, match="não está em revisão"):
        _approve(env, edited, command_id="cmd-apr-0003")
    with pytest.raises(RevisionConflictError):
        _submit(env, head, command_id="cmd-sub-0004")

    resubmitted = _submit(env, edited, command_id="cmd-sub-0005")
    second = _approve(env, resubmitted, command_id="cmd-apr-0004").value
    assert (second.revision, second.content_sha256) == (2, edited.content_sha256)


def test_request_changes_returns_draft_to_editing(env: CurationEnv) -> None:
    head = _submit(env, _draft_with_request(env))

    review = env.curation.review_draft(
        _meta("cmd-rev-0001", env.curator),
        draft_id=head.draft.draft_id,
        revision=head.revision,
        content_sha256=head.content_sha256,
        verdict="request_changes",
        justification="Definição precisa citar o método.",
    ).value

    assert review.verdict == "request_changes"
    assert env.curation.get_draft(head.draft.draft_id).state == "editing"
    assert _request_state(env) == "in_triage"


def test_rejected_draft_is_terminal(env: CurationEnv) -> None:
    head = _submit(env, _draft_with_request(env))
    env.curation.review_draft(
        _meta("cmd-rev-0002", env.curator),
        draft_id=head.draft.draft_id,
        revision=head.revision,
        content_sha256=head.content_sha256,
        verdict="reject",
        justification="Proposta não corresponde à fonte.",
    )

    draft = env.curation.get_draft(head.draft.draft_id)
    assert (draft.state, draft.closing_reason) == ("rejected", "Proposta não corresponde à fonte.")
    with pytest.raises(InvalidTransitionError):
        _edit(env, env.curation.get_head(head.draft.draft_id))


def test_blank_justification_is_an_invalid_command(env: CurationEnv) -> None:
    head = _submit(env, _draft_with_request(env))

    with pytest.raises(CommandValidationError, match="justification"):
        env.curation.review_draft(
            _meta("cmd-apr-0005", env.curator),
            draft_id=head.draft.draft_id,
            revision=head.revision,
            content_sha256=head.content_sha256,
            verdict="approve",
            justification="",
        )


def test_repeated_approval_command_returns_the_same_review(env: CurationEnv) -> None:
    head = _submit(env, _draft_with_request(env))
    first = _approve(env, head)
    events = len(env.curation.events())

    again = _approve(env, head)

    assert again.replayed is True
    assert again.value == first.value
    assert len(env.curation.events()) == events


def test_cancelling_an_approved_draft_invalidates_the_approval(env: CurationEnv) -> None:
    head = _submit(env, _draft_with_request(env))
    _approve(env, head)

    env.curation.cancel_draft(
        _meta("cmd-cnd-0001", env.curator), draft_id=head.draft.draft_id, reason="desistência"
    )

    draft = env.curation.get_draft(head.draft.draft_id)
    assert (draft.state, draft.approval_id) == ("cancelled", None)
    assert _request_state(env) == "in_triage"


def test_pending_carrier_proposal_blocks_submission_under_the_current_policy(
    env: CurationEnv,
) -> None:
    content = f.resolution_content()
    data = content.model_dump()
    for rows in data.values():
        for row in rows:
            if "lifecycle" in row:
                row["lifecycle"] = "draft"
    content = CatalogContent.model_validate(data)
    pending = next(b for b in content.bindings if b.id == R.B_AREA_PENDENTE)
    undetermined = IFCBinding.model_validate(
        {**pending.model_dump(), "carrier_kind": "property_or_quantity", "ifc_type": None}
    )
    content = content.model_copy(
        update={
            "bindings": (
                *(b for b in content.bindings if b.id != R.B_AREA_PENDENTE),
                undetermined,
            )
        }
    )
    head = _draft_with_request(env, content)

    with pytest.raises(ValidationGateError, match=r"carrier\.pending_proposal"):
        _submit(env, head)


@pytest.mark.parametrize("stage", ["in_review", "approved"])
def test_submitting_a_draft_that_is_not_being_edited_is_refused(
    env: CurationEnv, stage: str
) -> None:
    head = _submit(env, _draft_with_request(env))
    if stage == "approved":
        _approve(env, head)
    before = env.curation.get_draft(head.draft.draft_id)

    with pytest.raises(InvalidTransitionError):
        _submit(env, head, command_id="cmd-sub-0009")

    assert env.curation.get_draft(head.draft.draft_id) == before
