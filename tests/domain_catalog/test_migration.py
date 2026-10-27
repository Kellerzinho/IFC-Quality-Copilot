"""Adoção de catálogo E3.2b: plano imutável, confirmação explícita, pin, fila e recusas.

Componentes reais (autoridade SQLite, artefatos, publicação E2) e conteúdo
SINTÉTICO; atores sintéticos declarados. Nada aqui aprova conteúdo real.
"""

import os
import shutil
import uuid
from pathlib import Path

import pytest

pytest.importorskip("ifctester", reason="extra e3 não instalado (ifctester==0.8.5)")

from src.domain_catalog.diff_contracts import CatalogDiff
from src.domain_catalog.errors import CatalogComparisonError, CatalogPackageError
from src.domain_catalog.migration_contracts import MigrationError
from src.operations.project_service import commands
from src.operations.repositories import EventRepository, encode_document
from src.validation.analysis_identity import AnalysisRun, current_execution_profile
from tests.domain_catalog import factories as f
from tests.operations.adoption_env import (
    AdoptionEnv,
    apply,
    make_adoption_env,
    prepare,
    reanalyze,
    release_dir,
)
from tests.operations.e3_env import (
    approve_and_publish,
    meta,
    publish_first,
    publish_update,
)

DEFINITION = f.pt("Método sintético revisado para teste.")


@pytest.fixture
def aenv(tmp_path: Path) -> AdoptionEnv:
    return make_adoption_env(tmp_path, pairs=2)


def _runs(aenv: AdoptionEnv) -> list[AnalysisRun]:
    return aenv.adoption.list_runs(aenv.project_id)


def test_initial_adoption_pins_and_queues_one_run_per_active_pair(aenv: AdoptionEnv) -> None:
    receipt = publish_first(aenv.env, f.minimal_content("draft"))
    plan = prepare(aenv, receipt.release, "initial")

    assert plan.diff is None
    assert plan.diff_absent_reason == "no_previous_catalog"
    assert plan.target_provenance.state == "synthetic_test_published"
    assert plan.target_provenance.receipt_id == receipt.receipt_id
    assert [p.pair.pair_id for p in plan.pairs] == sorted(aenv.pairs, key=str)
    assert (plan.reanalysis_scope, plan.requirement_impact) == (
        "all_active_pairs",
        "conservative_all",
    )

    adoption = apply(aenv, plan)

    state = aenv.projects.load_project_state(aenv.project_id)
    assert adoption.status == "applied"
    assert state.pin is not None
    assert (state.pin_revision, state.pin.catalog) == (1, receipt.release)
    assert state.pin.catalog_provenance.state == "synthetic_test_published"
    runs = _runs(aenv)
    assert sorted(r.analysis_id for r in runs) == sorted(adoption.queued_analysis_ids)
    assert len(runs) == 2
    assert {r.state for r in runs} == {"queued"}
    assert {r.identity.pair_id for r in runs} == set(aenv.pairs)
    assert all(r.identity.catalog_state == "available" for r in runs)
    assert all(r.identity.pin_revision == 1 for r in runs)
    assert all(r.parent_analysis_id is None for r in runs)


def test_assistant_prepares_but_cannot_confirm(aenv: AdoptionEnv) -> None:
    receipt = publish_first(aenv.env, f.minimal_content("draft"))
    plan = prepare(aenv, receipt.release, "initial", actor=aenv.assistant)
    with pytest.raises(MigrationError) as refused:
        apply(aenv, plan, actor=aenv.assistant)
    assert refused.value.reason == "human_actor_required"
    assert aenv.projects.load_project_state(aenv.project_id).pin is None
    assert _runs(aenv) == []


def test_unpublished_package_and_loose_receipt_are_not_adoptable(
    aenv: AdoptionEnv, tmp_path: Path
) -> None:
    ref, folder = f.write_synthetic_release(tmp_path / "solto", f.minimal_content())
    with pytest.raises(MigrationError) as loose:
        prepare(aenv, ref, "initial", folder=folder)
    assert loose.value.reason == "unpublished_release"

    published = publish_first(aenv.env, f.minimal_content("draft"))
    with aenv.env.store.transaction() as uow:
        candidate = uow.curation.get("candidate", published.candidate_id)
        assert candidate is not None
        payload, digest = encode_document({**candidate.document, "state": "invalidated"})
        uow.connection.execute(
            "UPDATE curation_records SET payload = ?, payload_sha256 = ? "
            "WHERE kind = 'candidate' AND record_key = ?",
            (payload, digest, published.candidate_id),
        )
    with pytest.raises(MigrationError) as broken_chain:
        prepare(aenv, published.release, "initial")
    assert broken_chain.value.reason == "unpublished_release"


def test_synthetic_release_is_forbidden_in_operational_store(tmp_path: Path) -> None:
    aenv = make_adoption_env(tmp_path, purpose="operational")
    receipt = publish_first(aenv.env, f.minimal_content("draft"))
    with pytest.raises(MigrationError) as refused:
        prepare(aenv, receipt.release, "initial")
    assert refused.value.reason == "synthetic_catalog_forbidden"


def test_stale_tokens_and_altered_plan_hash_are_refused_without_effect(aenv: AdoptionEnv) -> None:
    receipt = publish_first(aenv.env, f.minimal_content("draft"))
    plan = prepare(aenv, receipt.release, "initial")
    with pytest.raises(MigrationError) as wrong_hash:
        apply(aenv, plan, plan_sha256="0" * 64)
    assert wrong_hash.value.reason == "plan_hash_mismatch"

    state = aenv.projects.load_project_state(aenv.project_id)
    first = state.pairs[0]
    aenv.projects.revise_pair(
        command=commands.revise_pair(
            uuid.uuid4(),
            aenv.human,
            aenv.project_id,
            first.pair_id,
            1,
            state.pair_set_revision,
            first.ifc,
            first.ids,
            False,
        ),
        pair_id=first.pair_id,
        expected_pair_revision=1,
        expected_pair_set_revision=state.pair_set_revision,
        ifc=first.ifc,
        ids=first.ids,
        active=False,
    )
    with pytest.raises(MigrationError) as stale_set:
        apply(aenv, plan)
    assert stale_set.value.reason == "stale_pair_set"

    fresh = prepare(aenv, receipt.release, "initial")
    competing = prepare(aenv, receipt.release, "initial")
    apply(aenv, fresh)
    with pytest.raises(MigrationError) as stale_pin:
        apply(aenv, competing)
    assert stale_pin.value.reason == "stale_pin"
    assert aenv.projects.load_project_state(aenv.project_id).pin_revision == 1


def test_update_and_rollback_create_new_identities_and_keep_history(aenv: AdoptionEnv) -> None:
    first = publish_first(aenv.env, f.minimal_content("draft"))
    pin1 = apply(aenv, prepare(aenv, first.release, "initial"))
    second = publish_update(
        aenv.env,
        first.release,
        (("concepts", f.concept("draft").model_copy(update={"definition": DEFINITION})),),
        "1.1.0",
    )
    update = prepare(aenv, second.release, "update")
    assert isinstance(update.diff, CatalogDiff)
    assert update.diff.old_ref == first.release
    assert [c.entity.kind for c in update.diff.entity_changes] == ["concepts"]
    assert update.diff_sha256 is not None
    pin2 = apply(aenv, update)
    rollback = prepare(aenv, first.release, "rollback")
    pin3 = apply(aenv, rollback)

    state = aenv.projects.load_project_state(aenv.project_id)
    assert state.pin is not None
    assert (state.pin_revision, state.pin.catalog, state.pin.previous_pin_revision) == (
        3,
        first.release,
        2,
    )
    runs = {r.analysis_id: r for r in _runs(aenv)}
    assert len(runs) == 6
    for previous, current in ((pin1, pin2), (pin2, pin3)):
        parents = {runs[a].parent_analysis_id for a in current.queued_analysis_ids}
        assert parents == set(previous.queued_analysis_ids)
    rolled = [runs[a] for a in pin3.queued_analysis_ids]
    original = [runs[a] for a in pin1.queued_analysis_ids]
    assert {r.identity.catalog_ref for r in rolled} == {first.release}
    assert {r.identity.pin_revision for r in rolled} == {3}
    assert not {r.analysis_id for r in rolled} & {r.analysis_id for r in original}
    assert {r.identity.pin_revision for r in original} == {1}


def test_noop_for_current_ref_and_replay_survives_later_adoptions(aenv: AdoptionEnv) -> None:
    first = publish_first(aenv.env, f.minimal_content("draft"))
    key = uuid.uuid4()
    initial_plan = prepare(aenv, first.release, "initial")
    original = apply(aenv, initial_plan, command_id=key)
    noop_plan = prepare(aenv, first.release, "update")
    assert noop_plan.diff is not None
    assert noop_plan.diff.no_changes
    assert noop_plan.diff.same_release
    noop = apply(aenv, noop_plan)
    assert (noop.status, noop.pin, noop.queued_analysis_ids) == ("noop", None, ())
    assert aenv.projects.load_project_state(aenv.project_id).pin_revision == 1
    assert len(_runs(aenv)) == 2

    second = publish_update(aenv.env, first.release, (), "1.0.1")
    apply(aenv, prepare(aenv, second.release, "update"))
    replay = apply(aenv, initial_plan, command_id=key)
    assert replay == original


def test_manifest_only_change_is_new_pin_not_noop(aenv: AdoptionEnv) -> None:
    first = publish_first(aenv.env, f.minimal_content("draft"))
    apply(aenv, prepare(aenv, first.release, "initial"))
    same_entities = publish_update(aenv.env, first.release, (), "1.0.1")
    plan = prepare(aenv, same_entities.release, "update")

    assert plan.diff is not None
    assert not plan.diff.has_entity_changes
    assert plan.diff.has_manifest_changes
    adoption = apply(aenv, plan)
    assert adoption.status == "applied"
    assert len(adoption.queued_analysis_ids) == 2


def test_version_hash_collision_is_refused_even_against_history(
    aenv: AdoptionEnv, tmp_path: Path
) -> None:
    first = publish_first(aenv.env, f.minimal_content("draft"))
    apply(aenv, prepare(aenv, first.release, "initial"))
    other = f.minimal_content().model_copy(
        update={"concepts": (f.concept().model_copy(update={"definition": DEFINITION}),)}
    )
    ref, folder = f.write_synthetic_release(tmp_path / "colide", other, version="1.0.0")
    assert ref.manifest_sha256 != first.release.manifest_sha256
    with pytest.raises(MigrationError) as collision:
        prepare(aenv, ref, "update", folder=folder)
    assert collision.value.reason == "version_hash_collision"


def test_distinct_catalog_and_missing_package_do_not_touch_the_pin(
    aenv: AdoptionEnv, tmp_path: Path
) -> None:
    first = publish_first(aenv.env, f.minimal_content("draft"))
    apply(aenv, prepare(aenv, first.release, "initial"))
    with pytest.raises(CatalogPackageError) as missing:
        prepare(aenv, first.release, "update", folder=tmp_path / "nao-existe")
    assert missing.value.reason == "not_found"

    other_catalog = f.catalog_identity().model_copy(
        update={"catalog_id": "urn:uuid:00000000-0000-4000-8000-0000000000e2"}
    )
    head = aenv.env.curation.import_draft(
        meta(aenv.env.importer),
        title="Outro catálogo sintético",
        catalog=other_catalog,
        content=f.minimal_content("draft"),
        source_label="fixture sintética",
        reason="outro catálogo",
    ).value
    foreign = approve_and_publish(aenv.env, head.draft.draft_id, "1.0.0")
    with pytest.raises(CatalogComparisonError) as distinct:
        prepare(aenv, foreign.release, "update")
    assert distinct.value.reason == "catalog_id_mismatch"
    state = aenv.projects.load_project_state(aenv.project_id)
    assert (state.pin_revision, state.pin.catalog if state.pin else None) == (1, first.release)


def test_intent_must_match_pin_state_and_rollback_history(aenv: AdoptionEnv) -> None:
    first = publish_first(aenv.env, f.minimal_content("draft"))
    with pytest.raises(MigrationError) as update_without_pin:
        prepare(aenv, first.release, "update")
    assert update_without_pin.value.reason == "intent_mismatch"
    apply(aenv, prepare(aenv, first.release, "initial"))
    with pytest.raises(MigrationError) as initial_with_pin:
        prepare(aenv, first.release, "initial")
    assert initial_with_pin.value.reason == "intent_mismatch"
    second = publish_update(aenv.env, first.release, (), "1.0.1")
    with pytest.raises(MigrationError) as never_pinned:
        prepare(aenv, second.release, "rollback")
    assert never_pinned.value.reason == "intent_mismatch"


def test_project_without_active_pairs_is_refused(tmp_path: Path) -> None:
    aenv = make_adoption_env(tmp_path, pairs=0)
    receipt = publish_first(aenv.env, f.minimal_content("draft"))
    with pytest.raises(MigrationError) as refused:
        prepare(aenv, receipt.release, "initial")
    assert refused.value.reason == "no_active_pairs"


def test_failure_in_apply_transaction_leaves_no_pin_run_or_command(
    aenv: AdoptionEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt = publish_first(aenv.env, f.minimal_content("draft"))
    plan = prepare(aenv, receipt.release, "initial")
    original = EventRepository.append

    def failing(self: EventRepository, namespace: str, document: dict[str, object]) -> int:
        if document.get("event") == "analysis_queued":
            from src.domain_catalog.draft_store import StoreUnavailableError

            raise StoreUnavailableError("falha simulada no evento de fila")
        return original(self, namespace, document)

    monkeypatch.setattr(EventRepository, "append", failing)
    key = uuid.uuid4()
    with pytest.raises(Exception, match="falha simulada"):
        apply(aenv, plan, command_id=key)
    monkeypatch.undo()
    assert aenv.projects.load_project_state(aenv.project_id).pin is None
    assert _runs(aenv) == []
    with aenv.env.store.transaction() as uow:
        assert uow.commands.get(str(key)) is None
    assert apply(aenv, plan, command_id=key).status == "applied"


def test_runtime_profile_mismatch_and_missing_artifact_refuse_apply(
    aenv: AdoptionEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt = publish_first(aenv.env, f.minimal_content("draft"))
    plan = prepare(aenv, receipt.release, "initial")
    import src.domain_catalog.migration as migration

    real = current_execution_profile()
    changed = real.model_copy(update={"condition_config_sha256": "f" * 64})
    monkeypatch.setattr(migration, "current_execution_profile", lambda limits=None: changed)
    with pytest.raises(MigrationError) as mismatch:
        apply(aenv, plan)
    assert mismatch.value.reason == "execution_profile_mismatch"
    monkeypatch.undo()

    retained = aenv.env.artifacts.catalog_dir(plan.target_retained)
    moved = retained.with_name(retained.name + "-movido")
    shutil.move(retained, moved)
    with pytest.raises(MigrationError) as missing:
        apply(aenv, plan)
    assert missing.value.reason == "artifact_unavailable"
    shutil.move(moved, retained)
    assert apply(aenv, plan).status == "applied"


def test_reanalysis_queues_without_changing_the_pin(aenv: AdoptionEnv) -> None:
    receipt = publish_first(aenv.env, f.minimal_content("draft"))
    first = apply(aenv, prepare(aenv, receipt.release, "initial"))
    queued = reanalyze(aenv)

    state = aenv.projects.load_project_state(aenv.project_id)
    assert state.pin_revision == 1
    runs = {r.analysis_id: r for r in _runs(aenv)}
    assert len(queued.queued_analysis_ids) == 2
    assert {runs[a].parent_analysis_id for a in queued.queued_analysis_ids} == set(
        first.queued_analysis_ids
    )
    assert {runs[a].identity.pin_revision for a in queued.queued_analysis_ids} == {1}
    assert release_dir(aenv, receipt.release).is_dir()


_FOREIGN = "urn:uuid:7a5f0000-0000-4000-8000-00000000f0f0"


@pytest.mark.parametrize(
    ("kind", "field", "value"),
    [
        ("review", "draft_id", _FOREIGN),
        ("review", "review_id", _FOREIGN),
        ("review", "justification", "outra justificativa"),
        ("revision", "draft_id", _FOREIGN),
        ("candidate", "candidate_id", _FOREIGN),
        ("intent", "intent_id", _FOREIGN),
        ("intent", "justification", "outra justificativa"),
    ],
)
def test_transplanted_node_breaks_the_exact_historical_chain(
    aenv: AdoptionEnv, kind: str, field: str, value: str
) -> None:
    """E3-12: um único campo de identidade/aresta transplantado (DTO válido) recusa a cadeia."""
    from src.domain_catalog.curation import revision_key

    published = publish_first(aenv.env, f.minimal_content("draft"))
    key = {
        "review": published.approval_id,
        "revision": revision_key(published.draft_id, published.revision),
        "candidate": published.candidate_id,
        "intent": published.intent_id,
    }[kind]
    with aenv.env.store.transaction() as uow:
        row = uow.curation.get(kind, key)
        assert row is not None
        assert row.document[field] != value
        uow.curation.replace(kind, key, row.version, {**row.document, field: value})
    with pytest.raises(MigrationError) as refused:
        prepare(aenv, published.release, "initial")
    assert refused.value.reason == "unpublished_release"


@pytest.mark.parametrize("damage", ["corrupted", "missing"])
def test_apply_reopens_the_old_retained_release_of_the_plan(aenv: AdoptionEnv, damage: str) -> None:
    """E3-13: old retido corrompido/ausente depois do prepare recusa o apply, sem efeito."""
    first = publish_first(aenv.env, f.minimal_content("draft"))
    apply(aenv, prepare(aenv, first.release, "initial"))
    second = publish_update(aenv.env, first.release, (), "1.0.1")
    plan = prepare(aenv, second.release, "update")
    assert plan.old_ref == first.release
    runs_before = len(_runs(aenv))

    from src.operations.analysis_queue import load_pin, retained_release

    with aenv.env.store.transaction() as uow:
        pin = load_pin(uow, aenv.project_id)
        assert pin is not None
        old_dir = aenv.env.artifacts.catalog_dir(retained_release(uow, pin))
    if damage == "corrupted":
        manifest = old_dir / "manifest.json"
        os.chmod(manifest, 0o644)
        manifest.write_bytes(manifest.read_bytes() + b" ")
        expected = "artifact_integrity_error"
    else:
        shutil.move(old_dir, old_dir.with_name(old_dir.name + "-movido"))
        expected = "artifact_unavailable"
    with pytest.raises(MigrationError) as refused:
        apply(aenv, plan)
    assert refused.value.reason == expected
    state = aenv.projects.load_project_state(aenv.project_id)
    assert state.pin_revision == 1
    assert len(_runs(aenv)) == runs_before


@pytest.mark.parametrize("field", ["expected_pin_revision", "expected_pair_set_revision"])
def test_prepare_refuses_non_int_tokens_before_any_effect(aenv: AdoptionEnv, field: str) -> None:
    """M-04: tokens bool nos argumentos públicos da adoção são ``invalid_command``."""
    receipt = publish_first(aenv.env, f.minimal_content("draft"))
    state = aenv.projects.load_project_state(aenv.project_id)
    arguments = {
        "expected_pin_revision": state.pin_revision,
        "expected_pair_set_revision": state.pair_set_revision,
    }
    arguments[field] = bool(arguments[field])
    with pytest.raises(MigrationError) as refused:
        aenv.adoption.prepare_catalog_adoption(
            project_id=aenv.project_id,
            target_ref=receipt.release,
            target_dir=release_dir(aenv, receipt.release),
            intent="initial",
            reason="tokens estritos",
            execution_profile=current_execution_profile(),
            prepared_by_actor_context_id=aenv.human,
            **arguments,
        )
    assert refused.value.reason == "invalid_command"
