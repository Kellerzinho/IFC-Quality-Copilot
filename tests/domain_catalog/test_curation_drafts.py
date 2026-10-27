"""Rascunhos de curadoria: criação, importação, edição e histórico (E2, M1-08).

Conteúdo, catálogo e atores SINTÉTICOS (``SYN_*``), gravados pelo adaptador de teste
não operacional. Verifica revisões imutáveis com hash, revisão esperada contra
sobrescrita concorrente, patch atômico com erro por campo, origem da proposta e
ausência de efeito parcial.
"""

from pathlib import Path

import pytest

from src.domain_catalog.content import CatalogContent
from src.domain_catalog.curation_errors import (
    ActorNotAllowedError,
    CommandValidationError,
    DraftPatchError,
    IdempotencyConflictError,
    InvalidTransitionError,
    RevisionConflictError,
)
from src.domain_catalog.curation_models import (
    CommandMeta,
    DraftHead,
    DraftPatch,
    DuplicateEntity,
    RemoveProposal,
    RequestedField,
    UpsertEntity,
    content_sha256,
)
from src.domain_catalog.draft_store import StoreUnavailableError
from tests.domain_catalog import factories as f
from tests.domain_catalog.curation_adapters import CurationEnv, make_env

CONCEPT_2 = "urn:uuid:00000000-0000-4000-8000-0000000d1001"
BINDING_COPY = "urn:uuid:00000000-0000-4000-8000-0000000d1002"


@pytest.fixture
def env(tmp_path: Path) -> CurationEnv:
    return make_env(tmp_path)


def _meta(command_id: str, actor: str) -> CommandMeta:
    return CommandMeta(command_id=command_id, actor_context_id=actor)


def _import(env: CurationEnv, content: CatalogContent | None = None) -> DraftHead:
    return env.curation.import_draft(
        _meta("cmd-imp-0001", env.importer),
        title="Proposta sintética importada",
        catalog=f.catalog_identity(),
        content=content if content is not None else f.minimal_content("draft"),
        source_label="fixture sintética de teste",
        reason="carga inicial de propostas sintéticas",
    ).value


def _new_concept_patch(code: str = "SYN_SEGUNDO") -> DraftPatch:
    concept = f._concept_for(CONCEPT_2, code, lifecycle="draft").model_dump(mode="json")
    return DraftPatch(
        operations=(UpsertEntity(op="upsert", kind="concepts", entity=concept),),
        reason="novo conceito proposto",
    )


def test_empty_draft_starts_at_revision_one_in_editing(env: CurationEnv) -> None:
    outcome = env.curation.create_draft(
        _meta("cmd-new-0001", env.curator),
        title="Catálogo sintético",
        catalog=f.catalog_identity(),
        reason="primeiro rascunho",
    )
    head = outcome.value

    assert head.draft.state == "editing"
    assert head.revision == 1
    assert head.content_sha256 == content_sha256(CatalogContent())
    assert env.curation.get_revision(head.draft.draft_id, 1).origin == "empty"
    assert outcome.receipt.revision == 1


def test_import_creates_draft_proposals_labelled_with_their_origin(env: CurationEnv) -> None:
    head = _import(env)
    revision = env.curation.get_revision(head.draft.draft_id, 1)

    assert revision.origin == "import"
    assert revision.created_by.actor_kind == "service"
    assert revision.operations == ("import fixture sintética de teste",)
    assert revision.content_sha256 == content_sha256(f.minimal_content("draft"))
    assert {c.lifecycle for c in revision.content.concepts} == {"draft"}


def test_import_refuses_approved_entities_and_records_nothing(env: CurationEnv) -> None:
    with pytest.raises(CommandValidationError, match="draft"):
        _import(env, f.minimal_content("approved"))

    assert env.curation.list_drafts() == ()
    assert env.curation.events() == ()


def test_editing_creates_a_new_immutable_revision(env: CurationEnv) -> None:
    head = _import(env)
    draft_id = head.draft.draft_id

    edited = env.curation.edit_draft(
        _meta("cmd-edt-0001", env.curator),
        draft_id=draft_id,
        expected_revision=1,
        patch=_new_concept_patch(),
    ).value

    assert edited.revision == 2
    assert edited.content_sha256 != head.content_sha256
    assert env.curation.get_revision(draft_id, 1).content == f.minimal_content("draft")
    second = env.curation.get_revision(draft_id, 2)
    assert second.origin == "human_edit"
    assert second.parent_revision == 1
    assert {c.id for c in second.content.concepts} == {f.CONCEPT_ID, CONCEPT_2}


def test_assistant_edit_is_labelled_as_assistant_proposal(env: CurationEnv) -> None:
    head = _import(env)

    env.curation.edit_draft(
        _meta("cmd-edt-0002", env.assistant),
        draft_id=head.draft.draft_id,
        expected_revision=1,
        patch=_new_concept_patch(),
    )

    revision = env.curation.get_revision(head.draft.draft_id, 2)
    assert revision.origin == "assistant_proposal"
    assert revision.created_by.actor_kind == "assistant"


def test_service_actor_cannot_edit_a_draft(env: CurationEnv) -> None:
    head = _import(env)

    with pytest.raises(ActorNotAllowedError):
        env.curation.edit_draft(
            _meta("cmd-edt-0003", env.importer),
            draft_id=head.draft.draft_id,
            expected_revision=1,
            patch=_new_concept_patch(),
        )


def test_stale_expected_revision_is_a_conflict_that_overwrites_nothing(env: CurationEnv) -> None:
    head = _import(env)
    draft_id = head.draft.draft_id
    env.curation.edit_draft(
        _meta("cmd-edt-0004", env.curator),
        draft_id=draft_id,
        expected_revision=1,
        patch=_new_concept_patch(),
    )

    with pytest.raises(RevisionConflictError) as conflict:
        env.curation.edit_draft(
            _meta("cmd-edt-0005", env.operator),
            draft_id=draft_id,
            expected_revision=1,
            patch=_new_concept_patch("SYN_CONCORRENTE"),
        )

    assert (conflict.value.expected, conflict.value.current) == (1, 2)
    assert env.curation.get_draft(draft_id).current_revision == 2
    assert env.curation.get_revision(draft_id, 2).content.concepts[-1].code == "SYN_SEGUNDO"


def test_invalid_operation_rejects_the_whole_patch_with_field_issues(env: CurationEnv) -> None:
    head = _import(env)
    valid = _new_concept_patch().operations[0]
    broken_binding = {**f.binding("draft").model_dump(mode="json"), "scope": "em_algum_lugar"}

    with pytest.raises(DraftPatchError) as caught:
        env.curation.edit_draft(
            _meta("cmd-edt-0006", env.curator),
            draft_id=head.draft.draft_id,
            expected_revision=1,
            patch=DraftPatch(
                operations=(
                    valid,
                    UpsertEntity(op="upsert", kind="bindings", entity=broken_binding),
                ),
                reason="um válido e um inválido",
            ),
        )

    assert [(i.code, i.field) for i in caught.value.issues] == [("invalid_entity", "scope")]
    assert env.curation.get_draft(head.draft.draft_id).current_revision == 1


def test_duplicating_a_binding_keeps_one_concept_and_flags_identity_review(
    env: CurationEnv,
) -> None:
    head = _import(env)

    env.curation.edit_draft(
        _meta("cmd-edt-0007", env.curator),
        draft_id=head.draft.draft_id,
        expected_revision=1,
        patch=DraftPatch(
            operations=(
                DuplicateEntity(
                    op="duplicate", kind="bindings", source_id=f.BINDING_ID, new_id=BINDING_COPY
                ),
            ),
            reason="duplicar linha para outro uso",
        ),
    )

    revision = env.curation.get_revision(head.draft.draft_id, 2)
    assert [c.id for c in revision.content.concepts] == [f.CONCEPT_ID]
    assert {b.concept_id for b in revision.content.bindings} == {f.CONCEPT_ID}
    report = env.curation.validate_draft(head.draft.draft_id)
    assert not report.passed
    assert any(
        x.code == "identity.unreviewed_duplicate" and x.entity_id == BINDING_COPY
        for x in report.findings
    )


def test_removing_a_proposal_is_a_new_revision(env: CurationEnv) -> None:
    head = _import(env)
    draft_id = head.draft.draft_id
    env.curation.edit_draft(
        _meta("cmd-edt-0008", env.curator),
        draft_id=draft_id,
        expected_revision=1,
        patch=_new_concept_patch(),
    )

    env.curation.edit_draft(
        _meta("cmd-edt-0009", env.curator),
        draft_id=draft_id,
        expected_revision=2,
        patch=DraftPatch(
            operations=(RemoveProposal(op="remove", kind="concepts", entity_id=CONCEPT_2),),
            reason="retirar proposta",
        ),
    )

    assert env.curation.get_revision(draft_id, 3).content == f.minimal_content("draft")
    assert [r.revision for r in env.curation.list_revisions(draft_id)] == [1, 2, 3]


def test_validation_report_is_bound_to_the_exact_revision(env: CurationEnv) -> None:
    head = _import(env)

    report = env.curation.validate_draft(head.draft.draft_id, 1)

    assert (report.revision, report.content_sha256) == (1, head.content_sha256)
    assert report.passed
    assert "source.synthetic_content" in {x.code for x in report.by_severity("warning")}


def test_replaying_an_edit_creates_no_second_revision(env: CurationEnv) -> None:
    head = _import(env)
    meta = _meta("cmd-edt-0010", env.curator)
    first = env.curation.edit_draft(
        meta, draft_id=head.draft.draft_id, expected_revision=1, patch=_new_concept_patch()
    )

    again = env.curation.edit_draft(
        meta, draft_id=head.draft.draft_id, expected_revision=1, patch=_new_concept_patch()
    )

    assert again.replayed is True
    assert again.receipt == first.receipt
    assert env.curation.get_draft(head.draft.draft_id).current_revision == 2


def test_reusing_an_edit_key_with_another_patch_is_a_conflict(env: CurationEnv) -> None:
    head = _import(env)
    meta = _meta("cmd-edt-0011", env.curator)
    env.curation.edit_draft(
        meta, draft_id=head.draft.draft_id, expected_revision=1, patch=_new_concept_patch()
    )

    with pytest.raises(IdempotencyConflictError):
        env.curation.edit_draft(
            meta,
            draft_id=head.draft.draft_id,
            expected_revision=1,
            patch=_new_concept_patch("SYN_OUTRO"),
        )


def test_store_failure_during_an_edit_keeps_the_previous_state(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    head = _import(env)
    events_before = env.curation.events()
    env.store.fail_at.add("insert:revision")

    with pytest.raises(StoreUnavailableError):
        env.curation.edit_draft(
            _meta("cmd-edt-0012", env.curator),
            draft_id=head.draft.draft_id,
            expected_revision=1,
            patch=_new_concept_patch(),
        )

    env.store.fail_at.clear()
    assert env.curation.get_draft(head.draft.draft_id) == head.draft
    assert env.curation.list_revisions(head.draft.draft_id)[-1].revision == 1
    assert env.curation.events() == events_before
    assert env.curation.get_command("cmd-edt-0012") is None


def test_cancelled_draft_cannot_be_edited(env: CurationEnv) -> None:
    head = _import(env)
    env.curation.cancel_draft(
        _meta("cmd-cnd-0001", env.curator), draft_id=head.draft.draft_id, reason="desistência"
    )

    with pytest.raises(InvalidTransitionError):
        env.curation.edit_draft(
            _meta("cmd-edt-0013", env.curator),
            draft_id=head.draft.draft_id,
            expected_revision=1,
            patch=_new_concept_patch(),
        )


def test_creating_a_draft_links_open_requests_of_the_same_catalog(env: CurationEnv) -> None:
    request = env.curation.request_change(
        _meta("cmd-req-0001", env.operator),
        catalog_id=f.SYN_CATALOG_ID,
        motivation="Campo sem cadastro.",
        field=RequestedField(field_name="SYN_Metodo"),
    ).value

    head = env.curation.create_draft(
        _meta("cmd-new-0002", env.curator),
        title="Atende a solicitação",
        catalog=f.catalog_identity(),
        request_ids=(request.request_id,),
        reason="atender pedido",
    ).value

    linked = env.curation.get_request(request.request_id)
    assert (linked.state, linked.draft_id) == ("in_triage", head.draft.draft_id)


def test_a_request_served_by_an_active_draft_cannot_be_linked_again(env: CurationEnv) -> None:
    request = env.curation.request_change(
        _meta("cmd-req-0002", env.operator),
        catalog_id=f.SYN_CATALOG_ID,
        motivation="Campo sem cadastro.",
        field=RequestedField(field_name="SYN_Metodo"),
    ).value
    env.curation.create_draft(
        _meta("cmd-new-0003", env.curator),
        title="Primeiro",
        catalog=f.catalog_identity(),
        request_ids=(request.request_id,),
        reason="atender",
    )

    with pytest.raises(InvalidTransitionError, match="rascunho ativo"):
        env.curation.create_draft(
            _meta("cmd-new-0004", env.curator),
            title="Segundo",
            catalog=f.catalog_identity(),
            request_ids=(request.request_id,),
            reason="atender de novo",
        )


def test_request_of_another_catalog_is_refused(env: CurationEnv) -> None:
    request = env.curation.request_change(
        _meta("cmd-req-0003", env.operator),
        catalog_id="urn:uuid:00000000-0000-4000-8000-00000000c0de",
        motivation="Outro catálogo.",
        field=RequestedField(field_name="X"),
    ).value

    with pytest.raises(CommandValidationError, match="outro catálogo"):
        env.curation.create_draft(
            _meta("cmd-new-0005", env.curator),
            title="Rascunho",
            catalog=f.catalog_identity(),
            request_ids=(request.request_id,),
            reason="atender",
        )
    assert env.curation.list_drafts() == ()
