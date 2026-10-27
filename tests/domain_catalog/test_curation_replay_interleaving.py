"""Repetição concluída entre a consulta inicial da chave e a leitura da base.

Intercalação determinística nas APIs públicas, com conteúdo e atores sintéticos.
O hook chama a consulta real depois que a segunda chamada e a publicação concluem.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from src.domain_catalog.contracts import CatalogReleaseRef
from src.domain_catalog.curation_errors import CommandValidationError, IdempotencyConflictError
from src.domain_catalog.curation_models import CommandMeta, CommandOutcome, DraftHead
from tests.domain_catalog import factories as f
from tests.domain_catalog.curation_adapters import CurationEnv, make_env
from tests.domain_catalog.test_publication import _approved, _meta, _prepare, _publish

OpenDraft = Callable[[CommandMeta, str], CommandOutcome[DraftHead]]


def _opener(env: CurationEnv, operation: str) -> OpenDraft:
    def create(meta: CommandMeta, title: str) -> CommandOutcome[DraftHead]:
        return env.curation.create_draft(
            meta, title=title, catalog=f.catalog_identity(), reason="teste de intercalação"
        )

    def imported(meta: CommandMeta, title: str) -> CommandOutcome[DraftHead]:
        return env.curation.import_draft(
            meta,
            title=title,
            catalog=f.catalog_identity(),
            content=f.minimal_content("draft"),
            source_label="fixture sintética",
            reason="teste de intercalação",
        )

    return create if operation == "create" else imported


@pytest.mark.parametrize("operation", ["create", "import"])
@pytest.mark.parametrize("concurrent", ["identical", "other_payload", "other_actor", "absent"])
def test_draft_opening_rechecks_key_when_concurrent_publication_invalidates_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str, concurrent: str
) -> None:
    env = make_env(tmp_path)
    candidate = _prepare(env, _approved(env, "release"), tag="release")
    actor = env.curator if operation == "create" else env.importer
    meta = _meta("cmd-interleaved-open", actor)
    open_draft = _opener(env, operation)
    latest_published = env.publication.latest_published
    completed: list[CommandOutcome[DraftHead]] = []
    event_counts: list[int] = []
    draft_counts: list[int] = []
    armed = True

    def interleaved_latest(catalog_id: str) -> CatalogReleaseRef | None:
        nonlocal armed
        if armed:
            armed = False
            if concurrent != "absent":
                other_meta = meta
                if concurrent == "other_actor":
                    other_actor = env.actors.register(
                        "human" if operation == "create" else "service", "Outro ator sintético"
                    )
                    other_meta = _meta(meta.command_id, other_actor)
                title = "Outro conteúdo" if concurrent == "other_payload" else "Mesmo conteúdo"
                completed.append(open_draft(other_meta, title))
            _publish(env, candidate, tag="release")
            event_counts.append(len(env.curation.events()))
            draft_counts.append(len(env.curation.list_drafts()))
        return latest_published(catalog_id)

    monkeypatch.setattr(env.publication, "latest_published", interleaved_latest)

    if concurrent == "identical":
        outcome = open_draft(meta, "Mesmo conteúdo")
        assert outcome.replayed is True
        assert outcome.receipt == completed[0].receipt
        assert outcome.value == completed[0].value
    elif concurrent == "absent":
        with pytest.raises(CommandValidationError, match="já tem release publicado"):
            open_draft(meta, "Mesmo conteúdo")
        assert env.curation.get_command(meta.command_id) is None
    else:
        with pytest.raises(IdempotencyConflictError):
            open_draft(meta, "Mesmo conteúdo")

    assert len(env.curation.events()) == event_counts[0]
    assert len(env.curation.list_drafts()) == draft_counts[0]
    if completed:
        recorded = env.curation.get_command(meta.command_id)
        assert recorded is not None
        assert recorded.receipt == completed[0].receipt
