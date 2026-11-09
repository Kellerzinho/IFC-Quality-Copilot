"""Dois escritores ao mesmo tempo (E2: testes de concorrência do plano M1-08 e M1-09).

Duas instâncias de serviço, como dois processos (cada uma com relógio e gerador de IDs
próprios), sobre o mesmo armazenamento de teste, em threads que começam juntas. Os
testes conferem invariantes, não a ordem de chegada:

- duas edições sobre a mesma revisão não se sobrescrevem;
- duas publicações do mesmo catálogo nunca bifurcam a linha de releases (achado E2-01);
- duas retomadas da mesma publicação geram um único recibo.

Conteúdo, catálogo e atores SINTÉTICOS; adaptadores de teste não operacionais. Não
certifica concorrência entre processos no Windows real nem o banco do M6.
"""

import threading
from collections.abc import Callable
from pathlib import Path

import pytest

from src.domain_catalog.curation_errors import (
    BaseSupersededError,
    CurationError,
    PublicationIncompleteError,
    PublicationInProgressError,
    RevisionConflictError,
)
from src.domain_catalog.curation_models import (
    CommandMeta,
    CommandOutcome,
    DraftHead,
    DraftPatch,
    PublicationReceipt,
    ReleaseCandidate,
    UpsertEntity,
)
from src.domain_catalog.package import ComponentTerms
from tests.domain_catalog import factories as f
from tests.domain_catalog.curation_adapters import CurationEnv, make_env

TERMS = (ComponentTerms(component="conteúdo", terms="sintético, sem terceiros"),)
CONCEPT_2 = "urn:uuid:00000000-0000-4000-8000-0000000d5001"


def _meta(command_id: str, actor: str) -> CommandMeta:
    return CommandMeta(command_id=command_id, actor_context_id=actor)


def _race(calls: dict[str, Callable[[], object]]) -> dict[str, object]:
    """Executa as chamadas em threads que começam juntas; devolve resultado ou exceção."""
    barrier = threading.Barrier(len(calls))
    outcomes: dict[str, object] = {}

    def run(name: str, call: Callable[[], object]) -> None:
        barrier.wait()
        try:
            outcomes[name] = call()
        except Exception as exc:
            outcomes[name] = exc

    threads = [threading.Thread(target=run, args=item) for item in calls.items()]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not any(thread.is_alive() for thread in threads)
    return outcomes


def _import(env: CurationEnv, tag: str) -> DraftHead:
    concept = f.concept("draft").model_copy(update={"definition": f.pt(f"Definição {tag}.")})
    return env.curation.import_draft(
        _meta(f"cmd-imp-{tag}", env.importer),
        title=f"Proposta sintética {tag}",
        catalog=f.catalog_identity(),
        content=f.minimal_content("draft").model_copy(update={"concepts": (concept,)}),
        source_label="fixture sintética",
        reason="propostas sintéticas",
    ).value


def _candidate(env: CurationEnv, tag: str, version: str) -> ReleaseCandidate:
    head = _import(env, tag)
    env.curation.submit_for_review(
        _meta(f"cmd-sub-{tag}", env.curator),
        draft_id=head.draft.draft_id,
        revision=1,
        content_sha256=head.content_sha256,
        reason="pronto",
    )
    env.curation.review_draft(
        _meta(f"cmd-apr-{tag}", env.curator),
        draft_id=head.draft.draft_id,
        revision=1,
        content_sha256=head.content_sha256,
        verdict="approve",
        justification="Conteúdo sintético conferido para o teste.",
    )
    return env.publication.prepare_release(
        _meta(f"cmd-prp-{tag}", env.curator),
        draft_id=head.draft.draft_id,
        revision=1,
        content_sha256=head.content_sha256,
        version=version,
        terms=TERMS,
        reason="preparar",
    ).value


def _publish(
    env: CurationEnv, candidate: ReleaseCandidate, tag: str
) -> CommandOutcome[PublicationReceipt]:
    return env.publication.publish(
        _meta(f"cmd-pub-{tag}", env.curator),
        candidate_id=candidate.candidate_id,
        version=candidate.release.version,
        manifest_sha256=candidate.release.manifest_sha256,
        justification="Publicação sintética de teste.",
    )


def test_two_concurrent_edits_of_the_same_revision_never_overwrite_each_other(
    tmp_path: Path,
) -> None:
    first = make_env(tmp_path)
    head = _import(first, "base")
    second = make_env(tmp_path, generation=2)

    def edit(env: CurationEnv, tag: str) -> CommandOutcome[DraftHead]:
        concept = f._concept_for(CONCEPT_2, f"SYN_{tag}", lifecycle="draft")
        return env.curation.edit_draft(
            _meta(f"cmd-edt-{tag}", env.curator),
            draft_id=head.draft.draft_id,
            expected_revision=1,
            patch=DraftPatch(
                operations=(
                    UpsertEntity(
                        op="upsert", kind="concepts", entity=concept.model_dump(mode="json")
                    ),
                ),
                reason=f"edição {tag}",
            ),
        )

    outcomes = _race({"A": lambda: edit(first, "A"), "B": lambda: edit(second, "B")})

    winners = [name for name, outcome in outcomes.items() if isinstance(outcome, CommandOutcome)]
    losers = [outcome for outcome in outcomes.values() if isinstance(outcome, Exception)]
    assert len(winners) == 1
    assert [type(error) for error in losers] == [RevisionConflictError]
    revisions = first.curation.list_revisions(head.draft.draft_id)
    assert [revision.revision for revision in revisions] == [1, 2]
    codes = {concept.code for concept in revisions[1].content.concepts}
    assert f"SYN_{winners[0]}" in codes
    assert len(codes & {"SYN_A", "SYN_B"}) == 1


def test_two_concurrent_publications_of_one_catalog_never_fork_its_history(
    tmp_path: Path,
) -> None:
    first = make_env(tmp_path)
    a = _candidate(first, "a", "1.0.0")
    b = _candidate(first, "b", "2.0.0")
    second = make_env(tmp_path, generation=2)

    outcomes = _race({"a": lambda: _publish(first, a, "a"), "b": lambda: _publish(second, b, "b")})

    receipts = [outcome for outcome in outcomes.values() if isinstance(outcome, CommandOutcome)]
    refusals = [outcome for outcome in outcomes.values() if isinstance(outcome, Exception)]
    assert len(receipts) == 1
    assert len(refusals) == 1
    assert isinstance(refusals[0], PublicationInProgressError | BaseSupersededError)
    (published,) = first.publication.list_published()
    assert published.previous_release is None
    report = first.publication.inspect()
    assert (report.pending_intents, report.unregistered_releases) == ((), ())


def test_two_concurrent_resumes_of_one_publication_record_a_single_receipt(
    tmp_path: Path,
) -> None:
    first = make_env(tmp_path, artifact_fail_at={"promote"})
    candidate = _candidate(first, "b", "1.0.0")
    with pytest.raises(PublicationIncompleteError) as stopped:
        _publish(first, candidate, "b")
    first.artifacts.fail_at.clear()
    second = make_env(tmp_path, generation=2)

    def resume(env: CurationEnv, tag: str) -> CommandOutcome[PublicationReceipt]:
        return env.publication.resume_publication(
            _meta(f"cmd-res-{tag}", env.curator),
            intent_id=stopped.value.intent_id,
            reason="retomar publicação interrompida",
        )

    outcomes = _race({"1": lambda: resume(first, "1"), "2": lambda: resume(second, "2")})

    receipts = [outcome for outcome in outcomes.values() if isinstance(outcome, CommandOutcome)]
    errors = [outcome for outcome in outcomes.values() if isinstance(outcome, Exception)]
    assert len(receipts) == 1
    assert all(isinstance(error, CurationError) for error in errors)
    assert [r.release for r in first.publication.list_published()] == [candidate.release]
    assert first.publication.open_published(candidate.release).ref == candidate.release
    assert first.publication.inspect().pending_intents == ()
