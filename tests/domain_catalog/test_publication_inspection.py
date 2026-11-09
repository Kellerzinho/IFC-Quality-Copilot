"""Inspeção somente leitura de preparos ativos, órfãos e resíduos conhecidos.

Fixtures e atores sintéticos, com adaptadores não operacionais. A cópia explícita
do preparo publicado representa o estado residual; não simula concorrência real.
"""

import hashlib
import shutil
from pathlib import Path
from typing import Literal

import pytest

from src.domain_catalog.curation_errors import PublicationIncompleteError
from src.domain_catalog.curation_models import DraftPatch, UpsertEntity
from tests.domain_catalog import factories as f
from tests.domain_catalog.curation_adapters import CurationEnv, make_env
from tests.domain_catalog.test_publication import _approved, _meta, _prepare, _publish


def _artifact_hashes(env: CurationEnv) -> dict[str, str]:
    return {
        str(path.relative_to(env.artifacts.root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(env.artifacts.root.rglob("*"))
        if path.is_file()
    }


@pytest.mark.parametrize("state", ["invalidated", "published"])
def test_known_terminal_staging_is_reported_and_preserved_after_restart(
    tmp_path: Path, state: Literal["invalidated", "published"]
) -> None:
    env = make_env(tmp_path)
    head = _approved(env)
    candidate = _prepare(env, head)
    staged = env.artifacts.staging_path(candidate.candidate_id)
    if state == "invalidated":
        concept = f.concept("draft").model_dump(mode="json")
        concept["definition"] = [{"lang": "pt-BR", "text": "Definição sintética revisada."}]
        env.curation.edit_draft(
            _meta("cmd-edit-inspect", env.curator),
            draft_id=head.draft.draft_id,
            expected_revision=head.revision,
            patch=DraftPatch(
                operations=(UpsertEntity(op="upsert", kind="concepts", entity=concept),),
                reason="revisão posterior ao preparo",
            ),
        )
    else:
        _publish(env, candidate)
        shutil.copytree(env.artifacts.release_path(candidate.release), staged)
    restarted = make_env(tmp_path, generation=2)
    events = restarted.curation.events()
    current_candidate = restarted.publication.get_candidate(candidate.candidate_id)
    current_draft = restarted.curation.get_head(head.draft.draft_id)
    receipts = restarted.publication.list_published()
    hashes = _artifact_hashes(restarted)

    report = restarted.publication.inspect()

    assert report.model_dump(mode="json").get("residual_staging") == [
        {"candidate_id": candidate.candidate_id, "state": state, "path": str(staged)}
    ]
    assert report.orphan_staging == ()
    assert report.pending_intents == ()
    assert report.damaged_publications == ()
    assert report.artifact_store_operational is False
    assert restarted.publication.inspect() == report
    assert _artifact_hashes(restarted) == hashes
    assert restarted.curation.events() == events
    assert restarted.publication.get_candidate(candidate.candidate_id) == current_candidate
    assert restarted.curation.get_head(head.draft.draft_id) == current_draft
    assert restarted.publication.list_published() == receipts
    if state == "published":
        assert restarted.publication.open_published(candidate.release).ref == candidate.release
    else:
        assert receipts == ()


@pytest.mark.parametrize("state", ["prepared", "publishing", "abandoned"])
def test_active_staging_is_not_reported_as_residual_or_orphan(tmp_path: Path, state: str) -> None:
    env = make_env(tmp_path)
    candidate = _prepare(env, _approved(env))
    if state != "prepared":
        env.artifacts.fail_at.add("promote")
        with pytest.raises(PublicationIncompleteError) as caught:
            _publish(env, candidate)
        if state == "abandoned":
            env.artifacts.fail_at.clear()
            env.publication.abandon_publication(
                _meta("cmd-abandon-inspect", env.curator),
                intent_id=caught.value.intent_id,
                reason="retomar depois, preservando preparo ativo",
            )

    report = env.publication.inspect()

    assert report.model_dump(mode="json").get("residual_staging") == []
    assert report.orphan_staging == ()
    assert len(report.pending_intents) == (1 if state == "publishing" else 0)
    assert env.artifacts.staging_path(candidate.candidate_id).is_dir()


def test_unregistered_staging_stays_orphan_without_becoming_a_known_residual(
    tmp_path: Path,
) -> None:
    env = make_env(tmp_path)
    candidate = _prepare(env, _approved(env))
    orphan = env.artifacts.staging_path(candidate.candidate_id).parent / "unknown"
    orphan.mkdir()
    (orphan / "partial.bin").write_bytes(b"incomplete synthetic fixture")
    hashes = _artifact_hashes(env)

    report = env.publication.inspect()

    assert report.orphan_staging == (str(orphan),)
    assert report.model_dump(mode="json").get("residual_staging") == []
    assert _artifact_hashes(env) == hashes


def test_published_candidate_without_staging_has_no_residual(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    candidate = _prepare(env, _approved(env))
    _publish(env, candidate)

    report = env.publication.inspect()

    assert report.model_dump(mode="json").get("residual_staging") == []
    assert report.orphan_staging == ()
    assert env.publication.open_published(candidate.release).ref == candidate.release
