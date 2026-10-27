"""Ensaio integrado M1-16: R1/A1 → R2/A2 → interrupções → backup → restauração → rollback.

Componentes REAIS (autoridade SQLite, artefatos, curadoria/publicação E2, adoção,
pipeline E3); projeto, atores, catálogo, IFC e IDS SINTÉTICOS e declarados. Publicar
aqui gera recibo técnico de bytes de teste, não aprovação de conteúdo real. A garantia
verificada é a do Windows local, processo único; rede e multiusuário não são cobertos.
"""

import hashlib
import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("ifctester", reason="extra e3 não instalado (ifctester==0.8.5)")

from src.artifacts.storage import LocalArtifactStore
from src.domain_catalog.curation_errors import PublicationIncompleteError
from src.domain_catalog.curation_models import CommandMeta, DraftPatch, UpsertEntity
from src.domain_catalog.errors import CatalogPackageError
from src.domain_catalog.migration import CatalogAdoptionService
from src.domain_catalog.migration_contracts import MigrationError
from src.operations.backup import (
    MANIFEST_NAME,
    BackupError,
    create_backup,
    restore_backup,
    verify_backup,
)
from src.operations.database import OperationalStore
from src.operations.project_service import ProjectService
from src.pipeline import run_catalog_analysis
from src.validation.catalog_analysis import load_analysis
from tests.operations import analysis_env as ae
from tests.operations.adoption_env import AdoptionEnv, apply, prepare
from tests.operations.e3_env import TERMS, approve_and_publish, meta, publish_first
from tests.suggestion_engine import m3_helpers as m


def _tree(path: Path) -> dict[str, str]:
    return {
        p.relative_to(path).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(path.rglob("*"))
        if p.is_file()
    }


def _execute(aenv: AdoptionEnv, analysis_ids: tuple[uuid.UUID, ...]) -> list[uuid.UUID]:
    for run in ae.runs_in_pair_order(aenv, analysis_ids):
        run_catalog_analysis(
            ae.request_for(run),
            store=aenv.env.store,
            artifacts=aenv.env.artifacts,
            operation_bundle=ae.operation_bundle(),
        )
    return list(analysis_ids)


def _db_rows(db: Path, table: str) -> list[Any]:
    connection = sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True)
    try:
        return connection.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
    finally:
        connection.close()


def test_integrated_update_interruptions_backup_restore_and_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    aenv = ae.make_analysis_env(tmp_path / "env")
    env = aenv.env

    # R1 → A1
    r1 = publish_first(env, ae.catalog())
    a1 = _execute(aenv, apply(aenv, prepare(aenv, r1.release, "initial")).queued_analysis_ids)
    r1_bytes = _tree(env.releases.release_path(r1.release))

    # Edição com resposta perdida: repetir a mesma chave não cria segunda revisão.
    head = env.curation.create_draft(
        meta(env.curator), title="Atualização sintética", base_release=r1.release, reason="r2"
    ).value
    edit_key = CommandMeta(command_id=str(uuid.uuid4()), actor_context_id=env.curator)
    patch = DraftPatch(
        operations=(
            UpsertEntity(
                op="upsert",
                kind="aliases",
                entity=ae.draft_entity(m.alias(sets=("SYN_Antigo",))).model_dump(mode="json"),
            ),
        ),
        reason="mudança sintética",
    )
    first = env.curation.edit_draft(
        edit_key, draft_id=head.draft.draft_id, expected_revision=1, patch=patch
    )
    again = env.curation.edit_draft(
        edit_key, draft_id=head.draft.draft_id, expected_revision=1, patch=patch
    )
    assert (first.replayed, again.replayed) == (False, True)
    assert len(env.curation.list_revisions(head.draft.draft_id)) == 2

    # Publicação de R2 interrompida na promoção: nada fica disponível nem adotável.
    current = env.curation.get_head(head.draft.draft_id)
    env.curation.submit_for_review(
        meta(env.curator),
        draft_id=current.draft.draft_id,
        revision=current.revision,
        content_sha256=current.content_sha256,
        reason="revisão sintética",
    )
    env.curation.review_draft(
        meta(env.curator),
        draft_id=current.draft.draft_id,
        revision=current.revision,
        content_sha256=current.content_sha256,
        verdict="approve",
        justification="Conteúdo sintético conferido apenas para teste técnico.",
    )
    candidate = env.publication.prepare_release(
        meta(env.curator),
        draft_id=current.draft.draft_id,
        revision=current.revision,
        content_sha256=current.content_sha256,
        version="1.1.0",
        terms=TERMS,
        reason="preparar release sintético",
    ).value
    publish_key = meta(env.curator)
    real_promote = env.releases.promote

    def interrupted(*args: object, **kwargs: object) -> Path:
        raise OSError(5, "falha simulada de disco")

    monkeypatch.setattr(env.releases, "promote", interrupted)
    with pytest.raises(PublicationIncompleteError):
        env.publication.publish(
            publish_key,
            candidate_id=candidate.candidate_id,
            version="1.1.0",
            manifest_sha256=candidate.release.manifest_sha256,
            justification="Publicação sintética de teste técnico.",
        )
    assert env.publication.latest_published(r1.release.catalog_id) == r1.release
    with pytest.raises((MigrationError, CatalogPackageError)):
        prepare(aenv, candidate.release, "update")
    assert aenv.projects.load_project_state(aenv.project_id).pin_revision == 1

    monkeypatch.setattr(env.releases, "promote", real_promote)
    r2 = env.publication.publish(
        publish_key,
        candidate_id=candidate.candidate_id,
        version="1.1.0",
        manifest_sha256=candidate.release.manifest_sha256,
        justification="Publicação sintética de teste técnico.",
    ).value
    assert r2.release == candidate.release
    r2_bytes = _tree(env.releases.release_path(r2.release))

    # Troca de pin interrompida: a transação não deixa pin nem análise.
    plan = prepare(aenv, r2.release, "update")
    from src.domain_catalog import migration

    real_event = migration.queued_event

    def failing_event(*args: object, **kwargs: object) -> object:
        raise RuntimeError("processo interrompido durante a troca de pin")

    monkeypatch.setattr(migration, "queued_event", failing_event)
    adoption_key = uuid.uuid4()
    with pytest.raises(RuntimeError):
        apply(aenv, plan, command_id=adoption_key)
    state = aenv.projects.load_project_state(aenv.project_id)
    assert state.pin_revision == 1
    assert state.pin is not None
    assert state.pin.catalog == r1.release
    assert len(aenv.adoption.list_runs(aenv.project_id)) == len(a1)

    monkeypatch.setattr(migration, "queued_event", real_event)
    adoption2 = apply(aenv, plan, command_id=adoption_key)
    assert adoption2.pin is not None
    assert adoption2.pin.pin_revision == 2
    a2 = _execute(aenv, adoption2.queued_analysis_ids)
    history = {a: load_analysis(env.store, a) for a in [*a1, *a2]}

    # Backup do corte coerente e restauração isolada.
    backup = tmp_path / "bk"
    manifest = create_backup(env.base, backup)
    assert all(not Path(entry.path).is_absolute() for entry in manifest.files)
    assert str(env.base) not in (backup / MANIFEST_NAME).read_text(encoding="utf-8")
    restored_root = tmp_path / "rs"
    restore_backup(backup, restored_root)

    store = OperationalStore.open(restored_root / "db")
    artifacts = LocalArtifactStore(restored_root / "a")
    assert store.purpose == "synthetic_test"
    for analysis_id, original in history.items():
        assert load_analysis(store, analysis_id) == original
    restored_state = ProjectService(store, artifacts).load_project_state(aenv.project_id)
    assert restored_state == aenv.projects.load_project_state(aenv.project_id)
    assert _tree(restored_root / "a" / "p") == _tree(env.base / "a" / "p")
    for table in ("events", "commands", "curation_records", "project_pin_revisions"):
        assert _db_rows(restored_root / "db" / "operations.sqlite3", table) == _db_rows(
            env.base / "db" / "operations.sqlite3", table
        )
    restored_runs = CatalogAdoptionService(store, artifacts).list_runs(aenv.project_id)
    assert [r.analysis_id for r in restored_runs] == [
        r.analysis_id for r in aenv.adoption.list_runs(aenv.project_id)
    ]

    # Rollback explícito na origem: novo pin, nova análise, histórico A1/A2 intacto.
    rollback = apply(aenv, prepare(aenv, r1.release, "rollback"))
    assert rollback.pin is not None
    assert rollback.pin.pin_revision == 3
    assert rollback.pin.previous_pin_revision == 2
    a3 = _execute(aenv, rollback.queued_analysis_ids)
    assert not set(a3) & set(history)
    for analysis_id, original in history.items():
        assert load_analysis(env.store, analysis_id) == original
    assert _tree(env.releases.release_path(r1.release)) == r1_bytes
    assert _tree(env.releases.release_path(r2.release)) == r2_bytes

    # A cópia continua no corte (pin r2) e íntegra depois da atividade na origem.
    verify_backup(backup)
    assert ProjectService(store, artifacts).load_project_state(aenv.project_id).pin_revision == 2


def test_backup_and_restore_refuse_unsafe_targets_and_detect_tampering(tmp_path: Path) -> None:
    aenv = ae.make_analysis_env(tmp_path / "env")
    publish_first(aenv.env, ae.catalog())
    backup = tmp_path / "bk"
    occupied = tmp_path / "ocupado"
    occupied.mkdir()
    (occupied / "x.txt").write_text("dado alheio", encoding="utf-8")

    with pytest.raises(BackupError):
        create_backup(aenv.env.base, occupied)
    assert (occupied / "x.txt").read_text(encoding="utf-8") == "dado alheio"
    with pytest.raises(BackupError):
        create_backup(tmp_path / "inexistente", tmp_path / "bk-x")

    create_backup(aenv.env.base, backup)
    with pytest.raises(BackupError):
        restore_backup(backup, occupied)
    assert sorted(p.name for p in occupied.iterdir()) == ["x.txt"]

    release_file = next(p for p in (backup / "a" / "p").rglob("*.json") if p.is_file())
    release_file.write_bytes(release_file.read_bytes() + b" ")
    with pytest.raises(BackupError, match="hash divergente"):
        verify_backup(backup)
    with pytest.raises(BackupError):
        restore_backup(backup, tmp_path / "rs")
    assert not (tmp_path / "rs").exists()

    (backup / "a" / "extra.bin").write_bytes(b"x")
    with pytest.raises(BackupError, match="divergem do manifesto"):
        verify_backup(backup)


def test_backup_without_manifest_or_with_unreadable_manifest_is_refused(tmp_path: Path) -> None:
    aenv = ae.make_analysis_env(tmp_path / "env")
    backup = tmp_path / "bk"
    create_backup(aenv.env.base, backup)
    manifest = backup / MANIFEST_NAME
    original = manifest.read_bytes()

    manifest.write_bytes(b'{"format": "outro"}\n')
    with pytest.raises(BackupError, match="manifesto ilegível"):
        verify_backup(backup)
    manifest.unlink()
    with pytest.raises(BackupError, match="sem manifesto"):
        verify_backup(backup)
    manifest.write_bytes(original)
    data = json.loads(original)
    assert data["guarantee"].startswith("processo único")
    verify_backup(backup)


def test_interrupted_publication_never_reaches_a_pin_and_retry_does_not_invent_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    aenv = ae.make_analysis_env(tmp_path / "env")
    env = aenv.env
    head = env.curation.import_draft(
        meta(env.importer),
        title="Release sintético",
        catalog=ae.f.catalog_identity(),
        content=ae.catalog(),
        source_label="fixture sintética",
        reason="conteúdo sintético",
    ).value
    real_promote = env.releases.promote

    def crash_after_promotion(candidate_id: str, ref: object) -> Path:
        real_promote(candidate_id, ref)  # type: ignore[arg-type]
        raise OSError(5, "processo interrompido depois de promover, antes do recibo")

    monkeypatch.setattr(env.releases, "promote", crash_after_promotion)
    with pytest.raises(PublicationIncompleteError):
        approve_and_publish(env, head.draft.draft_id, "1.0.0")
    assert env.publication.list_published() == ()
    (pending,) = env.publication.inspect().pending_intents
    assert pending.promoted is True
    assert env.releases.release_path(pending.release).is_dir()
    reviews = env.curation.list_reviews(head.draft.draft_id)
    assert [r.verdict for r in reviews] == ["approve"]

    with pytest.raises(MigrationError) as refused:
        prepare(aenv, pending.release, "initial")
    assert refused.value.reason == "unpublished_release"
    assert aenv.projects.load_project_state(aenv.project_id).pin is None
    assert env.curation.list_reviews(head.draft.draft_id) == reviews


def test_backup_and_restore_refuse_targets_nested_with_their_origin(tmp_path: Path) -> None:
    aenv = ae.make_analysis_env(tmp_path / "env")
    with pytest.raises(BackupError, match="dentro da origem"):
        create_backup(aenv.env.base, aenv.env.base / "a" / "copia")
    assert not (aenv.env.base / "a" / "copia").exists()
    backup = tmp_path / "bk"
    create_backup(aenv.env.base, backup)
    with pytest.raises(BackupError, match="dentro da origem"):
        restore_backup(backup, backup / "restaurado")
    verify_backup(backup)
