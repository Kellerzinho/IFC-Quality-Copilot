"""Candidatos do perfil E4 pela curadoria E2 existente (Task 3).

O conteúdo REAL entra só como rascunho num serviço SINTÉTICO sobre adaptadores de
teste não operacionais; nenhum teste aprova, prepara ou publica conteúdo da Daiane.
A integração com publicação usa conteúdo SINTÉTICO (``factories``).
"""

from pathlib import Path

import pytest

from src.domain_catalog.content import CatalogContent, validate_content
from src.domain_catalog.curation_errors import CommandValidationError, IdempotencyConflictError
from src.domain_catalog.curation_models import CommandMeta, content_sha256
from src.domain_catalog.draft_store import StoreUnavailableError
from src.domain_catalog.errors import CatalogValidationError
from src.domain_catalog.importers.daiane import MATRIX_PATH, import_appendix_a, load_matrix
from src.domain_catalog.importers.daiane_b import APPENDIX_B_PATH, load_appendix_b
from src.domain_catalog.profile import CANDIDATES_PATH, PDF_SHA256, load_candidates
from tests.domain_catalog import factories as f
from tests.domain_catalog.curation_adapters import make_env
from tests.domain_catalog.test_curation_daiane import TEST_CATALOG


@pytest.fixture(scope="module")
def candidates() -> CatalogContent:
    appendix_a = import_appendix_a(load_matrix(MATRIX_PATH))
    appendix_b = load_appendix_b(APPENDIX_B_PATH, expected_pdf_sha256=PDF_SHA256)
    return load_candidates(CANDIDATES_PATH, appendix_a, appendix_b)


def _meta(command_id: str, actor: str) -> CommandMeta:
    return CommandMeta(command_id=command_id, actor_context_id=actor)


@pytest.mark.external_data
def test_real_candidates_are_refused_for_release(candidates: CatalogContent) -> None:
    with pytest.raises(CatalogValidationError):
        validate_content(candidates, for_release=True)


@pytest.mark.external_data
def test_real_candidates_enter_curation_only_as_draft(
    tmp_path: Path, candidates: CatalogContent
) -> None:
    env = make_env(tmp_path)
    head = env.curation.import_draft(
        _meta("cmd-e4-dai", env.importer),
        title="Perfil Daiane E4 — candidatos (teste)",
        catalog=TEST_CATALOG,
        content=candidates,
        source_label="data/catalogs/profiles/daiane-e4/candidates-v1.json",
        reason="levar os candidatos E4 ao fluxo de curadoria, sem aprovar",
    ).value

    assert env.curation.get_revision(head.draft.draft_id, 1).content == candidates
    assert head.content_sha256 == content_sha256(candidates)
    assert head.draft.state == "editing"
    assert env.publication.list_published() == ()


def test_synthetic_import_is_idempotent_and_payload_collision_is_refused(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    content = f.minimal_content("draft")
    first = env.curation.import_draft(
        _meta("cmd-syn", env.importer),
        title="Sintético",
        catalog=f.catalog_identity(),
        content=content,
        source_label="fixture sintética",
        reason="teste",
    )
    events = env.curation.events()
    replay = env.curation.import_draft(
        _meta("cmd-syn", env.importer),
        title="Sintético",
        catalog=f.catalog_identity(),
        content=content,
        source_label="fixture sintética",
        reason="teste",
    )

    assert replay.value == first.value
    assert env.curation.events() == events
    with pytest.raises(IdempotencyConflictError):
        env.curation.import_draft(
            _meta("cmd-syn", env.importer),
            title="Outro",
            catalog=f.catalog_identity(),
            content=content,
            source_label="fixture sintética",
            reason="teste",
        )
    assert env.curation.events() == events


def test_failed_import_leaves_no_partial_event(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    before = env.curation.events()
    env.store.fail_at.add("before_commit")

    with pytest.raises(StoreUnavailableError, match="before_commit"):
        env.curation.import_draft(
            _meta("cmd-falha", env.importer),
            title="Sintético",
            catalog=f.catalog_identity(),
            content=f.minimal_content("draft"),
            source_label="fixture sintética",
            reason="teste",
        )
    env.store.fail_at.clear()
    assert env.curation.events() == before
    assert env.curation.list_drafts() == ()


def test_approved_entities_are_never_imported(tmp_path: Path) -> None:
    env = make_env(tmp_path)

    with pytest.raises(CommandValidationError, match="draft"):
        env.curation.import_draft(
            _meta("cmd-aprovado", env.importer),
            title="Sintético",
            catalog=f.catalog_identity(),
            content=f.minimal_content("approved"),
            source_label="fixture sintética",
            reason="teste",
        )
