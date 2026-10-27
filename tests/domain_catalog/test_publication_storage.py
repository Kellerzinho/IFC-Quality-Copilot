"""Falhas do armazenamento de releases como erro tipado (E2, M1-09; achado E2-03).

A porta ``ReleaseArtifactStore`` não deixa ``OSError`` cru atravessar: pasta obstruída,
acesso negado ou disco cheio saem como ``ArtifactStoreError`` com a etapa (``phase``), o
``errno`` e a causa encadeada, sem o caminho completo na mensagem (plano M6 §4.3 e
§12.1). O serviço também normaliza, para o caso de um adaptador que não cumpra a porta.
Falha não vira sucesso nem remove o obstáculo: o preparo que falha não registra candidato
nem comando, e o que ficou no disco aparece em ``inspect()``; o abandono continua gravado
mesmo que a quarentena falhe, e repetir o comando a conclui.

Conteúdo, catálogo e atores SINTÉTICOS; as obstruções são reais, em pastas temporárias
do adaptador de teste não operacional. Acesso negado e disco cheio são simulados pela
exceção que o sistema operacional levantaria, no ponto de escrita do adaptador.
"""

import dataclasses
import errno
from pathlib import Path

import pytest

from src.domain_catalog.curation import CurationService
from src.domain_catalog.curation_errors import CurationError, PublicationIncompleteError
from src.domain_catalog.curation_models import (
    CommandMeta,
    CommandOutcome,
    DraftHead,
    PublicationReceipt,
    ReleaseCandidate,
)
from src.domain_catalog.package import ComponentTerms, ReleaseFiles
from src.domain_catalog.publication import (
    ArtifactStoreError,
    PublicationService,
    StoreInventory,
)
from tests.domain_catalog import curation_adapters
from tests.domain_catalog import factories as f
from tests.domain_catalog.curation_adapters import (
    TEST_LIMITS,
    CurationEnv,
    LocalTestReleaseStore,
    make_env,
)

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


def _prepare(env: CurationEnv, head: DraftHead) -> ReleaseCandidate:
    return env.publication.prepare_release(
        _meta("cmd-prp-1", env.curator),
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


def _assert_typed(error: ArtifactStoreError, phase: str, code: int, tmp_path: Path) -> None:
    """Erro tipado da etapa, com errno e causa encadeada, sem o caminho completo."""
    assert isinstance(error, CurationError)
    assert (error.code, error.phase, error.errno) == ("artifact_store", phase, code)
    assert isinstance(error.__cause__, OSError)
    assert str(tmp_path) not in str(error)


# --- obstrução real ------------------------------------------------------------------------


def test_obstructed_staging_area_is_a_typed_error_that_records_nothing(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    head = _approved(env)
    env.artifacts.root.mkdir(parents=True)
    obstruction = env.artifacts.root / "s"
    obstruction.write_bytes(b"obstrucao sintetica")

    with pytest.raises(ArtifactStoreError) as caught:
        _prepare(env, head)

    _assert_typed(caught.value, "stage", errno.EEXIST, tmp_path)
    assert obstruction.read_bytes() == b"obstrucao sintetica"
    assert env.curation.get_draft(head.draft.draft_id).candidate_id is None
    assert env.curation.get_command("cmd-prp-1") is None
    obstruction.unlink()
    assert _prepare(env, head).state == "prepared"


def test_obstructed_release_area_interrupts_publication_with_a_typed_error(
    tmp_path: Path,
) -> None:
    env = make_env(tmp_path)
    candidate = _prepare(env, _approved(env))
    obstruction = env.artifacts.root / "r"
    obstruction.write_bytes(b"obstrucao sintetica")

    with pytest.raises(PublicationIncompleteError) as caught:
        _publish(env, candidate)

    assert caught.value.phase == "promote"
    assert isinstance(caught.value.__cause__, ArtifactStoreError)
    assert obstruction.read_bytes() == b"obstrucao sintetica"
    assert env.publication.list_published() == ()
    obstruction.unlink()
    assert _publish(env, candidate).value.release == candidate.release


def test_obstructed_quarantine_keeps_the_abandonment_and_a_repeat_finishes_it(
    tmp_path: Path,
) -> None:
    env = make_env(tmp_path, artifact_fail_at={"after_promote"})
    candidate = _prepare(env, _approved(env))
    with pytest.raises(PublicationIncompleteError) as stopped:
        _publish(env, candidate)
    env.artifacts.fail_at.clear()
    obstruction = env.artifacts.root / "q"
    obstruction.write_bytes(b"obstrucao sintetica")
    meta = _meta("cmd-abd-1", env.curator)

    with pytest.raises(ArtifactStoreError) as caught:
        env.publication.abandon_publication(
            meta, intent_id=stopped.value.intent_id, reason="abandonar com quarentena obstruída"
        )

    _assert_typed(caught.value, "quarantine", errno.EEXIST, tmp_path)
    assert env.publication.get_intent(stopped.value.intent_id).state == "abandoned"
    final = env.artifacts.release_path(candidate.release)
    assert final.is_dir()
    obstruction.unlink()
    again = env.publication.abandon_publication(
        meta, intent_id=stopped.value.intent_id, reason="abandonar com quarentena obstruída"
    )
    assert again.replayed is True
    assert not final.exists()
    assert len(env.artifacts.quarantined()) == 1


CANDIDATE_ID = "urn:uuid:00000000-0000-4000-9000-000000000099"


@pytest.mark.parametrize(
    ("area", "phase", "codes"),
    [
        ("s", "stage", {errno.EEXIST}),
        ("r", "promote", {errno.EEXIST, errno.ENOTDIR}),
        ("q", "quarantine", {errno.EEXIST}),
    ],
    ids=["preparo", "releases", "quarentena"],
)
def test_test_release_store_honours_the_error_obligation_of_the_port(
    tmp_path: Path, area: str, phase: str, codes: set[int]
) -> None:
    """Obrigação da porta, direto no adaptador de teste (referência para o adaptador do M6)."""
    store = LocalTestReleaseStore(tmp_path / "a")
    files = f.build_synthetic_release(f.minimal_content("approved"))
    if area != "s":
        store.stage(CANDIDATE_ID, files)
    store.root.mkdir(parents=True, exist_ok=True)
    (store.root / area).write_bytes(b"obstrucao sintetica")

    def operate() -> Path:
        if area == "s":
            return store.stage(CANDIDATE_ID, files)
        if area == "r":
            return store.promote(CANDIDATE_ID, files.ref)
        return store.quarantine(store.staging_path(CANDIDATE_ID), "teste")

    with pytest.raises(ArtifactStoreError) as caught:
        operate()

    error = caught.value
    assert (error.phase, isinstance(error.__cause__, OSError)) == (phase, True)
    assert error.errno in codes
    assert str(tmp_path) not in str(error)
    assert (store.root / area).read_bytes() == b"obstrucao sintetica"


def test_stray_file_in_the_release_area_is_reported_not_raised(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    _publish(env, _prepare(env, _approved(env)))
    stray = env.artifacts.root / "r" / "solto.txt"
    stray.write_text("arquivo solto", encoding="utf-8")

    report = env.publication.inspect()

    assert report.unregistered_releases == (str(stray),)
    assert report.damaged_publications == ()


# --- acesso negado e disco cheio -------------------------------------------------------------


@pytest.mark.parametrize(
    ("failure", "code"),
    [(PermissionError, errno.EACCES), (OSError, errno.ENOSPC)],
    ids=["acesso-negado", "disco-cheio"],
)
def test_denied_access_or_full_disk_while_staging_is_typed_and_records_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: type[OSError], code: int
) -> None:
    env = make_env(tmp_path)
    head = _approved(env)

    def failing_write(path: Path, data: bytes) -> None:
        raise failure(code, "falha simulada do sistema operacional", str(path))

    monkeypatch.setattr(curation_adapters, "_write_durably", failing_write)

    with pytest.raises(ArtifactStoreError) as caught:
        _prepare(env, head)

    _assert_typed(caught.value, "stage", code, tmp_path)
    assert env.curation.get_draft(head.draft.draft_id).candidate_id is None
    assert env.curation.get_command("cmd-prp-1") is None
    assert len(env.publication.inspect().orphan_staging) == 1


# --- adaptador que não cumpre a porta ---------------------------------------------------------


class _LeakyReleaseStore(LocalTestReleaseStore):
    """Adaptador que NÃO cumpre a porta: deixa ``OSError`` cru escapar nos pontos pedidos."""

    def __init__(self, root: Path, leak_at: set[str]) -> None:
        super().__init__(root)
        self.leak_at = leak_at

    def _leak(self, point: str, code: int) -> None:
        if point in self.leak_at:
            raise OSError(code, "falha crua do sistema operacional", str(self.root / point))

    def stage(self, candidate_id: str, release: ReleaseFiles) -> Path:
        self._leak("stage", errno.EACCES)
        return super().stage(candidate_id, release)

    def quarantine(self, path: Path, label: str) -> Path:
        self._leak("quarantine", errno.ENOSPC)
        return super().quarantine(path, label)

    def inventory(self) -> StoreInventory:
        self._leak("inventory", errno.EACCES)
        return super().inventory()


def _env_with(env: CurationEnv, artifacts: LocalTestReleaseStore) -> CurationEnv:
    publication = PublicationService(
        env.store, env.actors, artifacts, clock=env.clock, new_id=env.new_id, limits=TEST_LIMITS
    )
    curation = CurationService(
        env.store, env.actors, releases=publication, clock=env.clock, new_id=env.new_id
    )
    return dataclasses.replace(env, artifacts=artifacts, curation=curation, publication=publication)


def test_service_normalizes_raw_os_errors_from_a_nonconforming_store(tmp_path: Path) -> None:
    base = make_env(tmp_path)
    leaky = _LeakyReleaseStore(base.artifacts.root, {"stage"})
    env = _env_with(base, leaky)
    head = _approved(env)

    with pytest.raises(ArtifactStoreError) as staging:
        _prepare(env, head)
    _assert_typed(staging.value, "stage", errno.EACCES, tmp_path)
    assert env.curation.get_command("cmd-prp-1") is None

    leaky.leak_at = {"inventory"}
    with pytest.raises(ArtifactStoreError) as inspecting:
        env.publication.inspect()
    _assert_typed(inspecting.value, "inspect", errno.EACCES, tmp_path)

    leaky.leak_at = set()
    leaky.fail_at = {"after_promote"}
    candidate = _prepare(env, head)
    with pytest.raises(PublicationIncompleteError) as stopped:
        _publish(env, candidate)
    leaky.fail_at = set()
    leaky.leak_at = {"quarantine"}
    with pytest.raises(ArtifactStoreError) as quarantining:
        env.publication.abandon_publication(
            _meta("cmd-abd-1", env.curator),
            intent_id=stopped.value.intent_id,
            reason="abandonar com disco cheio",
        )
    _assert_typed(quarantining.value, "quarantine", errno.ENOSPC, tmp_path)
    assert env.publication.get_intent(stopped.value.intent_id).state == "abandoned"
