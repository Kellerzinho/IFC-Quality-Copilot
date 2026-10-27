"""Repetição exata de comandos depois que o estado mudou (E2, M1-08; achado E2-02).

Pelo protocolo de idempotência (plano M6 §6.3), a chave é procurada antes das
pré-condições de uma execução nova. Repetir exatamente o mesmo comando (chave,
operação, conteúdo e contexto de ator) devolve o recibo gravado, ainda que depois um
release tenha sido publicado, a base tenha sido superada, o serviço tenha reiniciado
ou o release-base tenha deixado de abrir. Resposta perdida nunca vira recusa; um
comando novo continua passando por todas as pré-condições.

Conteúdo, catálogo e atores SINTÉTICOS, sobre os adaptadores de teste não operacionais.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from src.domain_catalog.content import CatalogContent
from src.domain_catalog.contracts import CatalogReleaseRef
from src.domain_catalog.curation_errors import CommandValidationError
from src.domain_catalog.curation_models import (
    CommandMeta,
    CommandOutcome,
    DraftHead,
    DraftPatch,
    ReleaseCandidate,
    ReviewRecord,
    UpsertEntity,
)
from src.domain_catalog.errors import CatalogPackageError
from src.domain_catalog.package import ComponentTerms
from tests.domain_catalog import factories as f
from tests.domain_catalog.curation_adapters import CurationEnv, make_env

TERMS = (ComponentTerms(component="conteúdo", terms="sintético, sem terceiros"),)
CONCEPT_2 = "urn:uuid:00000000-0000-4000-8000-0000000d4001"
CONCEPT_3 = "urn:uuid:00000000-0000-4000-8000-0000000d4002"

Opener = Callable[[CommandMeta, CatalogReleaseRef | None], CommandOutcome[DraftHead]]


def _meta(command_id: str, actor: str) -> CommandMeta:
    return CommandMeta(command_id=command_id, actor_context_id=actor)


def _concept_patch(concept_id: str, code: str) -> DraftPatch:
    concept = f._concept_for(concept_id, code, lifecycle="draft").model_dump(mode="json")
    return DraftPatch(
        operations=(UpsertEntity(op="upsert", kind="concepts", entity=concept),),
        reason="acrescentar conceito sintético",
    )


def _import_first(env: CurationEnv, tag: str) -> DraftHead:
    return env.curation.import_draft(
        _meta(f"cmd-imp-{tag}", env.importer),
        title=f"Proposta sintética {tag}",
        catalog=f.catalog_identity(),
        content=f.minimal_content("draft"),
        source_label="fixture sintética",
        reason="propostas sintéticas",
    ).value


def _evolution(env: CurationEnv, base: CatalogReleaseRef, tag: str) -> DraftHead:
    head = env.curation.create_draft(
        _meta(f"cmd-new-{tag}", env.curator),
        title=f"Evolução {tag}",
        base_release=base,
        reason="nova versão",
    ).value
    return env.curation.edit_draft(
        _meta(f"cmd-edt-{tag}", env.curator),
        draft_id=head.draft.draft_id,
        expected_revision=head.revision,
        patch=_concept_patch(CONCEPT_2, f"SYN_{tag.upper()}"),
    ).value


def _publish_draft(env: CurationEnv, head: DraftHead, version: str, tag: str) -> ReleaseCandidate:
    """Submete, aprova (curador sintético), prepara e publica o rascunho."""
    env.curation.submit_for_review(
        _meta(f"cmd-sub-{tag}", env.curator),
        draft_id=head.draft.draft_id,
        revision=head.revision,
        content_sha256=head.content_sha256,
        reason="pronto",
    )
    env.curation.review_draft(
        _meta(f"cmd-apr-{tag}", env.curator),
        draft_id=head.draft.draft_id,
        revision=head.revision,
        content_sha256=head.content_sha256,
        verdict="approve",
        justification="Conteúdo sintético conferido para o teste.",
    )
    candidate = env.publication.prepare_release(
        _meta(f"cmd-prp-{tag}", env.curator),
        draft_id=head.draft.draft_id,
        revision=head.revision,
        content_sha256=head.content_sha256,
        version=version,
        terms=TERMS,
        reason="preparar release sintético",
    ).value
    env.publication.publish(
        _meta(f"cmd-pub-{tag}", env.curator),
        candidate_id=candidate.candidate_id,
        version=version,
        manifest_sha256=candidate.release.manifest_sha256,
        justification="Publicação sintética de teste.",
    )
    return candidate


def _opener(env: CurationEnv, operation: str) -> tuple[Opener, str]:
    """Abre rascunho vazio (``create``) ou importado (``import``) e o ator de cada um."""

    def create(meta: CommandMeta, base: CatalogReleaseRef | None) -> CommandOutcome[DraftHead]:
        return env.curation.create_draft(
            meta,
            title="Rascunho sintético",
            catalog=f.catalog_identity() if base is None else None,
            base_release=base,
            reason="teste de repetição",
        )

    def imported(meta: CommandMeta, base: CatalogReleaseRef | None) -> CommandOutcome[DraftHead]:
        addition = f._concept_for(CONCEPT_3, "SYN_IMPORTADO", lifecycle="draft")
        content = (
            f.minimal_content("draft") if base is None else CatalogContent(concepts=(addition,))
        )
        return env.curation.import_draft(
            meta,
            title="Importação sintética",
            catalog=f.catalog_identity(),
            content=content,
            source_label="fixture sintética",
            base_release=base,
            reason="teste de repetição",
        )

    if operation == "create":
        return create, env.curator
    return imported, env.importer


@pytest.mark.parametrize("operation", ["create", "import"])
def test_replaying_a_draft_opening_after_a_release_returns_the_original_receipt(
    tmp_path: Path, operation: str
) -> None:
    env = make_env(tmp_path)
    open_draft, actor = _opener(env, operation)
    meta = _meta("cmd-abrir-0001", actor)
    original = open_draft(meta, None)
    _publish_draft(env, _import_first(env, "outro"), "1.0.0", "outro")
    drafts = env.curation.list_drafts()
    events = env.curation.events()

    replay = open_draft(meta, None)

    assert replay.replayed is True
    assert (replay.receipt, replay.value) == (original.receipt, original.value)
    assert env.curation.list_drafts() == drafts
    assert env.curation.events() == events
    with pytest.raises(CommandValidationError, match="já tem release publicado"):
        open_draft(_meta("cmd-abrir-0002", actor), None)


@pytest.mark.parametrize("operation", ["create", "import"])
def test_replaying_a_draft_opening_on_a_superseded_base_returns_the_original_receipt(
    tmp_path: Path, operation: str
) -> None:
    env = make_env(tmp_path)
    first = _publish_draft(env, _import_first(env, "r1"), "1.0.0", "r1")
    open_draft, actor = _opener(env, operation)
    meta = _meta("cmd-abrir-base", actor)
    original = open_draft(meta, first.release)
    _publish_draft(env, _evolution(env, first.release, "r2"), "1.1.0", "r2")

    replay = open_draft(meta, first.release)

    assert replay.replayed is True
    assert (replay.receipt, replay.value) == (original.receipt, original.value)
    with pytest.raises(CommandValidationError, match="não é o último publicado"):
        open_draft(_meta("cmd-abrir-base-2", actor), first.release)


@pytest.mark.parametrize("operation", ["create", "import"])
def test_replaying_a_draft_opening_after_a_restart_returns_the_original_receipt(
    tmp_path: Path, operation: str
) -> None:
    env = make_env(tmp_path)
    open_draft, actor = _opener(env, operation)
    meta = _meta("cmd-abrir-0001", actor)
    original = open_draft(meta, None)
    _publish_draft(env, _import_first(env, "outro"), "1.0.0", "outro")

    restarted = make_env(tmp_path, generation=2)
    reopen, same_actor = _opener(restarted, operation)
    replay = reopen(_meta("cmd-abrir-0001", same_actor), None)

    assert same_actor == actor
    assert replay.replayed is True
    assert (replay.receipt, replay.value) == (original.receipt, original.value)


class _DraftCommands:
    """Editar, submeter e aprovar um rascunho sobre release-base, com chaves fixas."""

    def __init__(self, env: CurationEnv, draft_id: str) -> None:
        self.env = env
        self.draft_id = draft_id
        self.patch = _concept_patch(CONCEPT_2, "SYN_SEGUNDO")
        self.edited_sha256 = ""

    def edit(self) -> CommandOutcome[DraftHead]:
        outcome = self.env.curation.edit_draft(
            _meta("cmd-edt-r2", self.env.curator),
            draft_id=self.draft_id,
            expected_revision=1,
            patch=self.patch,
        )
        self.edited_sha256 = outcome.value.content_sha256
        return outcome

    def submit(self) -> CommandOutcome[DraftHead]:
        return self.env.curation.submit_for_review(
            _meta("cmd-sub-r2", self.env.curator),
            draft_id=self.draft_id,
            revision=2,
            content_sha256=self.edited_sha256,
            reason="pronto",
        )

    def review(self) -> CommandOutcome[ReviewRecord]:
        return self.env.curation.review_draft(
            _meta("cmd-apr-r2", self.env.curator),
            draft_id=self.draft_id,
            revision=2,
            content_sha256=self.edited_sha256,
            verdict="approve",
            justification="Conteúdo sintético conferido para o teste.",
        )


@pytest.mark.parametrize("step", ["edit", "submit", "review"])
def test_replaying_a_draft_command_does_not_reread_the_base_release(
    tmp_path: Path, step: str
) -> None:
    env = make_env(tmp_path)
    first = _publish_draft(env, _import_first(env, "r1"), "1.0.0", "r1")
    head = env.curation.create_draft(
        _meta("cmd-new-r2", env.curator),
        title="Evolução",
        base_release=first.release,
        reason="nova versão",
    ).value
    commands = _DraftCommands(env, head.draft.draft_id)
    edited, submitted, reviewed = commands.edit(), commands.submit(), commands.review()
    damaged = env.artifacts.release_path(first.release) / "concepts.json"
    damaged.write_bytes(damaged.read_bytes() + b" ")
    with pytest.raises(CatalogPackageError):
        env.publication.open_published(first.release)

    if step == "edit":
        replay_edit = commands.edit()
        assert replay_edit.replayed is True
        assert (replay_edit.receipt, replay_edit.value) == (edited.receipt, edited.value)
    elif step == "submit":
        replay_submit = commands.submit()
        assert replay_submit.replayed is True
        assert (replay_submit.receipt, replay_submit.value) == (submitted.receipt, submitted.value)
    else:
        replay_review = commands.review()
        assert replay_review.replayed is True
        assert (replay_review.receipt, replay_review.value) == (reviewed.receipt, reviewed.value)
    assert env.curation.get_draft(head.draft.draft_id).state == "approved"
