"""Falhas, retomada e reconciliação da publicação (E2: M1-09 e parte do M1-16).

Conteúdo e atores SINTÉTICOS, em pastas temporárias dos adaptadores de teste não
operacionais. As falhas são injetadas nos pontos nomeados dos adaptadores. Verifica
que nenhuma falha deixa release parcial disponível, que a intenção identifica o que
retomar ou abandonar, que nada é sobrescrito nem apagado e que bytes adulterados
nunca são publicados. Durabilidade em disco real do Windows não é certificada aqui.
"""

import hashlib
from pathlib import Path

import pytest

from src.domain_catalog.curation_errors import (
    CurationNotFoundError,
    InvalidTransitionError,
    PublicationIncompleteError,
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
from src.domain_catalog.draft_store import StoreUnavailableError
from src.domain_catalog.errors import CatalogPackageError
from src.domain_catalog.package import ComponentTerms
from src.domain_catalog.publication import ArtifactStoreError
from tests.domain_catalog import factories as f
from tests.domain_catalog.curation_adapters import CurationEnv, make_env

TERMS = (ComponentTerms(component="conteúdo", terms="sintético, sem terceiros"),)


def _meta(command_id: str, actor: str) -> CommandMeta:
    return CommandMeta(command_id=command_id, actor_context_id=actor)


def _approved(env: CurationEnv) -> DraftHead:
    head = env.curation.import_draft(
        _meta("cmd-imp-1", env.importer),
        title="Proposta sintética",
        catalog=f.catalog_identity(),
        content=f.minimal_content("draft"),
        source_label="fixture sintética",
        reason="propostas sintéticas",
    ).value
    env.curation.submit_for_review(
        _meta("cmd-sub-1", env.curator),
        draft_id=head.draft.draft_id,
        revision=1,
        content_sha256=head.content_sha256,
        reason="pronto",
    )
    env.curation.review_draft(
        _meta("cmd-apr-1", env.curator),
        draft_id=head.draft.draft_id,
        revision=1,
        content_sha256=head.content_sha256,
        verdict="approve",
        justification="Conteúdo sintético conferido para o teste.",
    )
    return env.curation.get_head(head.draft.draft_id)


def _prepare(env: CurationEnv, head: DraftHead, command_id: str = "cmd-prp-1") -> ReleaseCandidate:
    return env.publication.prepare_release(
        _meta(command_id, env.curator),
        draft_id=head.draft.draft_id,
        revision=head.revision,
        content_sha256=head.content_sha256,
        version="1.0.0",
        terms=TERMS,
        reason="preparar",
    ).value


def _publish(
    env: CurationEnv, candidate: ReleaseCandidate, command_id: str = "cmd-pub-1"
) -> CommandOutcome[PublicationReceipt]:
    return env.publication.publish(
        _meta(command_id, env.curator),
        candidate_id=candidate.candidate_id,
        version=candidate.release.version,
        manifest_sha256=candidate.release.manifest_sha256,
        justification="Publicação sintética de teste.",
    )


def _hashes(path: Path) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(path.iterdir())}


# --- candidato ----------------------------------------------------------------------------


def test_failure_before_staging_records_no_candidate_and_retry_works(tmp_path: Path) -> None:
    env = make_env(tmp_path, artifact_fail_at={"stage"})
    head = _approved(env)

    with pytest.raises(ArtifactStoreError):
        _prepare(env, head)

    assert env.curation.get_draft(head.draft.draft_id).candidate_id is None
    assert env.artifacts.staged_dirs() == ()
    env.artifacts.fail_at.clear()
    assert _prepare(env, head).state == "prepared"


def test_partial_staging_is_an_orphan_reported_and_kept(tmp_path: Path) -> None:
    env = make_env(tmp_path, artifact_fail_at={"stage_partial"})
    head = _approved(env)

    with pytest.raises(ArtifactStoreError):
        _prepare(env, head)

    (orphan,) = env.publication.inspect().orphan_staging
    env.artifacts.fail_at.clear()
    candidate = _prepare(env, head)
    assert candidate.state == "prepared"
    assert env.publication.inspect().orphan_staging == (orphan,)
    assert Path(orphan).is_dir()


def test_store_failure_after_staging_leaves_no_candidate(tmp_path: Path) -> None:
    env = make_env(tmp_path, fail_at={"insert:candidate"})
    head = _approved(env)

    with pytest.raises(StoreUnavailableError):
        _prepare(env, head)

    env.store.fail_at.clear()
    assert env.curation.get_draft(head.draft.draft_id).candidate_id is None
    assert len(env.publication.inspect().orphan_staging) == 1
    assert env.curation.get_command("cmd-prp-1") is None


# --- intenção e promoção ----------------------------------------------------------------


def test_store_failure_recording_the_intent_changes_nothing(tmp_path: Path) -> None:
    env = make_env(tmp_path, fail_at={"insert:intent"})
    candidate = _prepare(env, _approved(env))

    with pytest.raises(StoreUnavailableError):
        _publish(env, candidate)

    env.store.fail_at.clear()
    assert env.publication.get_candidate(candidate.candidate_id).state == "prepared"
    assert env.curation.get_command("cmd-pub-1") is None
    assert env.publication.inspect().pending_intents == ()
    assert _publish(env, candidate).value.release == candidate.release


def test_failure_during_promotion_publishes_nothing_and_the_same_command_resumes(
    tmp_path: Path,
) -> None:
    env = make_env(tmp_path, artifact_fail_at={"promote"})
    head = _approved(env)
    candidate = _prepare(env, head)

    with pytest.raises(PublicationIncompleteError) as stopped:
        _publish(env, candidate)

    assert stopped.value.phase == "promote"
    assert env.publication.latest_published(f.SYN_CATALOG_ID) is None
    with pytest.raises(CurationNotFoundError):
        env.publication.open_published(candidate.release)
    assert env.curation.get_draft(head.draft.draft_id).state == "publishing"
    (pending,) = env.publication.inspect().pending_intents
    assert (pending.staged_valid, pending.promoted) == (True, False)
    with pytest.raises(InvalidTransitionError):
        env.curation.edit_draft(
            _meta("cmd-edt-1", env.curator),
            draft_id=head.draft.draft_id,
            expected_revision=1,
            patch=DraftPatch(
                operations=(
                    UpsertEntity(
                        op="upsert",
                        kind="concepts",
                        entity=f.concept("draft")
                        .model_copy(update={"code": "SYN_X"})
                        .model_dump(mode="json"),
                    ),
                ),
                reason="editar durante a publicação",
            ),
        )

    env.artifacts.fail_at.clear()
    resumed = _publish(env, candidate)

    assert resumed.replayed is False
    assert env.publication.latest_published(f.SYN_CATALOG_ID) == candidate.release
    assert env.publication.inspect().pending_intents == ()


def test_crash_after_promotion_is_completed_by_another_person_after_restart(
    tmp_path: Path,
) -> None:
    env = make_env(tmp_path, artifact_fail_at={"after_promote"})
    candidate = _prepare(env, _approved(env))
    with pytest.raises(PublicationIncompleteError) as stopped:
        _publish(env, candidate)
    final = env.artifacts.release_path(candidate.release)
    assert final.is_dir()
    assert env.publication.latest_published(f.SYN_CATALOG_ID) is None

    restarted = make_env(tmp_path, generation=2)
    (pending,) = restarted.publication.inspect().pending_intents
    assert (pending.promoted, pending.promoted_valid) == (True, True)
    other = restarted.actors.register("human", "Outra Pessoa Sintética")
    receipt = restarted.publication.resume_publication(
        _meta("cmd-res-1", other),
        intent_id=stopped.value.intent_id,
        reason="retomar publicação interrompida",
    ).value

    assert receipt.published_by.declared_name == "Pessoa Curadora Sintética"
    assert receipt.completed_by.declared_name == "Outra Pessoa Sintética"
    assert restarted.publication.latest_published(f.SYN_CATALOG_ID) == candidate.release
    original = restarted.curation.get_command("cmd-pub-1")
    assert original is not None
    assert original.state == "completed"


def test_store_failure_writing_the_receipt_keeps_the_release_unavailable(
    tmp_path: Path,
) -> None:
    env = make_env(tmp_path, fail_at={"insert:publication"})
    candidate = _prepare(env, _approved(env))

    with pytest.raises(PublicationIncompleteError) as stopped:
        _publish(env, candidate)

    assert stopped.value.phase == "receipt"
    assert env.artifacts.release_path(candidate.release).is_dir()
    with pytest.raises(CurationNotFoundError):
        env.publication.open_published(candidate.release)
    env.store.fail_at.clear()
    receipt = _publish(env, candidate).value
    assert receipt.release == candidate.release


def test_abandoning_quarantines_the_unreceipted_release_and_allows_a_new_attempt(
    tmp_path: Path,
) -> None:
    env = make_env(tmp_path, artifact_fail_at={"after_promote"})
    head = _approved(env)
    candidate = _prepare(env, head)
    with pytest.raises(PublicationIncompleteError) as stopped:
        _publish(env, candidate)
    env.artifacts.fail_at.clear()

    intent = env.publication.abandon_publication(
        _meta("cmd-abd-1", env.curator),
        intent_id=stopped.value.intent_id,
        reason="interrupção; tentar de novo",
    ).value

    assert intent.state == "abandoned"
    assert not env.artifacts.release_path(candidate.release).exists()
    (quarantined,) = env.artifacts.quarantined()
    assert (quarantined / "manifest.json").is_file()
    assert env.publication.get_candidate(candidate.candidate_id).state == "prepared"
    assert env.curation.get_draft(head.draft.draft_id).state == "approved"
    with pytest.raises(InvalidTransitionError, match="abandonada"):
        _publish(env, candidate)
    receipt = _publish(env, candidate, "cmd-pub-2").value
    assert receipt.release == candidate.release
    assert env.publication.inspect().unregistered_releases == ()


# --- bytes adulterados e destino ocupado ---------------------------------------------------


def test_tampered_staging_is_quarantined_and_never_published(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    candidate = _prepare(env, _approved(env))
    staged = env.artifacts.staged_path(candidate.candidate_id)
    assert staged is not None
    concepts = staged / "concepts.json"
    concepts.write_bytes(concepts.read_bytes().replace(b"SYN_METODO", b"SYN_ALTERADO"))

    _publish(env, candidate)

    published = env.publication.open_published(candidate.release)
    assert published.content.concepts[0].code == "SYN_METODO"
    (quarantined,) = env.artifacts.quarantined()
    assert b"SYN_ALTERADO" in (quarantined / "concepts.json").read_bytes()


def test_unexpected_file_in_staging_never_reaches_the_release(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    candidate = _prepare(env, _approved(env))
    staged = env.artifacts.staged_path(candidate.candidate_id)
    assert staged is not None
    (staged / "operacao.py").write_text("import os\n", encoding="utf-8")

    _publish(env, candidate)

    final = env.artifacts.release_path(candidate.release)
    assert not (final / "operacao.py").exists()
    (quarantined,) = env.artifacts.quarantined()
    assert (quarantined / "operacao.py").is_file()


def test_foreign_directory_at_the_destination_is_never_overwritten(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    candidate = _prepare(env, _approved(env))
    final = env.artifacts.release_path(candidate.release)
    final.mkdir(parents=True)
    (final / "manifest.json").write_bytes(b"{}\n")

    with pytest.raises(PublicationIncompleteError) as stopped:
        _publish(env, candidate)

    assert stopped.value.phase == "verify_existing"
    assert (final / "manifest.json").read_bytes() == b"{}\n"
    (pending,) = env.publication.inspect().pending_intents
    assert (pending.promoted, pending.promoted_valid) == (True, False)
    env.publication.abandon_publication(
        _meta("cmd-abd-1", env.curator),
        intent_id=stopped.value.intent_id,
        reason="destino ocupado por pasta desconhecida",
    )
    (quarantined,) = env.artifacts.quarantined()
    assert (quarantined / "manifest.json").read_bytes() == b"{}\n"


def test_damaged_published_release_is_reported_and_never_opens_as_empty(
    tmp_path: Path,
) -> None:
    env = make_env(tmp_path)
    candidate = _prepare(env, _approved(env))
    _publish(env, candidate)
    target = env.artifacts.release_path(candidate.release) / "bindings.json"
    target.write_bytes(target.read_bytes() + b" ")

    with pytest.raises(CatalogPackageError) as caught:
        env.publication.open_published(candidate.release)

    assert caught.value.reason == "integrity"
    assert env.publication.inspect().damaged_publications == (
        f"{candidate.release.catalog_id} {candidate.release.version}",
    )


def test_inspection_changes_nothing(tmp_path: Path) -> None:
    env = make_env(tmp_path, artifact_fail_at={"after_promote"})
    candidate = _prepare(env, _approved(env))
    with pytest.raises(PublicationIncompleteError):
        _publish(env, candidate)
    events = env.curation.events()
    final_hashes = _hashes(env.artifacts.release_path(candidate.release))

    first = env.publication.inspect()
    second = env.publication.inspect()

    assert first == second
    assert env.curation.events() == events
    assert _hashes(env.artifacts.release_path(candidate.release)) == final_hashes


def test_published_state_survives_a_restart(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    candidate = _prepare(env, _approved(env))
    receipt = _publish(env, candidate).value

    restarted = make_env(tmp_path, generation=2)

    assert restarted.publication.list_published() == (receipt,)
    assert restarted.publication.open_published(candidate.release).ref == candidate.release


def test_candidate_bytes_are_reopened_after_staging(tmp_path: Path) -> None:
    env = make_env(tmp_path, artifact_fail_at={"stage_corrupt"})
    head = _approved(env)

    with pytest.raises(CatalogPackageError) as caught:
        _prepare(env, head)

    assert caught.value.reason == "integrity"
    assert env.curation.get_draft(head.draft.draft_id).candidate_id is None
    assert env.curation.get_command("cmd-prp-1") is None


def test_promoted_bytes_are_verified_before_the_receipt(tmp_path: Path) -> None:
    env = make_env(tmp_path, artifact_fail_at={"promote_corrupt"})
    candidate = _prepare(env, _approved(env))

    with pytest.raises(PublicationIncompleteError) as stopped:
        _publish(env, candidate)

    assert stopped.value.phase == "verify_promoted"
    assert env.publication.latest_published(f.SYN_CATALOG_ID) is None
    (pending,) = env.publication.inspect().pending_intents
    assert (pending.promoted, pending.promoted_valid) == (True, False)


def test_abandonment_is_recorded_before_the_disk_is_touched(tmp_path: Path) -> None:
    env = make_env(tmp_path, artifact_fail_at={"after_promote"})
    head = _approved(env)
    candidate = _prepare(env, head)
    with pytest.raises(PublicationIncompleteError) as stopped:
        _publish(env, candidate)
    env.artifacts.fail_at = {"quarantine"}
    meta = _meta("cmd-abd-1", env.curator)

    with pytest.raises(ArtifactStoreError):
        env.publication.abandon_publication(
            meta, intent_id=stopped.value.intent_id, reason="abandonar com disco falhando"
        )

    assert env.publication.get_intent(stopped.value.intent_id).state == "abandoned"
    assert env.publication.get_candidate(candidate.candidate_id).state == "prepared"
    assert env.curation.get_draft(head.draft.draft_id).state == "approved"
    final = env.artifacts.release_path(candidate.release)
    assert final.is_dir()
    assert env.publication.inspect().unregistered_releases == (str(final),)
    env.artifacts.fail_at.clear()
    again = env.publication.abandon_publication(
        meta, intent_id=stopped.value.intent_id, reason="abandonar com disco falhando"
    )
    assert again.replayed is True
    assert not final.exists()
    assert len(env.artifacts.quarantined()) == 1


def test_repeating_an_old_abandonment_never_touches_a_new_publication_in_progress(
    tmp_path: Path,
) -> None:
    env = make_env(tmp_path, artifact_fail_at={"after_promote"})
    candidate = _prepare(env, _approved(env))
    with pytest.raises(PublicationIncompleteError) as first:
        _publish(env, candidate)
    old = _meta("cmd-abd-1", env.curator)
    env.publication.abandon_publication(
        old, intent_id=first.value.intent_id, reason="primeira tentativa abandonada"
    )
    with pytest.raises(PublicationIncompleteError) as second:
        _publish(env, candidate, "cmd-pub-2")
    final = env.artifacts.release_path(candidate.release)
    assert final.is_dir()

    replayed = env.publication.abandon_publication(
        old, intent_id=first.value.intent_id, reason="primeira tentativa abandonada"
    )

    assert replayed.replayed is True
    assert final.is_dir()
    assert env.publication.get_intent(second.value.intent_id).state == "recorded"
    assert len(env.artifacts.quarantined()) == 1
