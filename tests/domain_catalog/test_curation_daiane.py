"""Amostra REAL da Daiane (rascunho da E1) dentro do fluxo de curadoria da E2.

O rascunho real entra só como rascunho, importado por um serviço sintético no adaptador
de teste não operacional. **Nenhum teste aqui aprova, prepara ou publica conteúdo da
Daiane**: a aprovação curatorial desse conteúdo é de Felipe/curador, fora dos testes. A
identidade de catálogo usada é provisória e de teste. Verifica que os três usos de
``Area_Forma`` atravessam o armazenamento sem perder a pendência, que a escrita continua
bloqueada e que reconciliar o portador exige decidir a divergência.
"""

from pathlib import Path

import pytest

from src.domain_catalog.content import CatalogContent
from src.domain_catalog.curation_errors import (
    DraftPatchError,
    InvalidTransitionError,
    ValidationGateError,
)
from src.domain_catalog.curation_models import (
    CommandMeta,
    DraftHead,
    DraftPatch,
    UpsertEntity,
    content_sha256,
)
from src.domain_catalog.curation_validation import PENDING_CARRIER_POLICY
from src.domain_catalog.importers.daiane import (
    E1_DRAFT_PATH,
    MATRIX_PATH,
    DaianeImport,
    import_appendix_a,
    load_daiane_draft,
    load_matrix,
)
from src.domain_catalog.package import CatalogIdentity, ComponentTerms
from tests.domain_catalog.curation_adapters import CurationEnv, make_env

TEST_CATALOG = CatalogIdentity(
    catalog_id="urn:uuid:00000000-0000-4000-8000-0000000da1e2",
    namespace="ifcqc.teste.e2.amostra-real",
    namespace_status="provisional",
    name="Catálogo de TESTE para exercitar o rascunho real da E1",
    maintainer="testes automatizados (não é curadoria)",
    language="pt-BR",
)
AREA_FORMA_BINDINGS = (
    "urn:uuid:5edb32e2-94ef-4bf1-b0f9-b71f9acff832",
    "urn:uuid:dd2276ee-fbaa-44e0-9c48-8b2c34687c4e",
    "urn:uuid:f479f781-6821-4d29-86e0-cec9b150fcb4",
)
AREA_FORMA_DECISION = "urn:uuid:acbdec55-6250-4d8a-ae36-78abcd05fbbb"


@pytest.fixture(scope="module")
def daiane_draft() -> CatalogContent:
    imported: DaianeImport = import_appendix_a(load_matrix(MATRIX_PATH))
    return load_daiane_draft(E1_DRAFT_PATH, imported)


@pytest.fixture
def env(tmp_path: Path) -> CurationEnv:
    return make_env(tmp_path)


def _meta(command_id: str, actor: str) -> CommandMeta:
    return CommandMeta(command_id=command_id, actor_context_id=actor)


def _import(env: CurationEnv, content: CatalogContent) -> DraftHead:
    return env.curation.import_draft(
        _meta("cmd-imp-dai", env.importer),
        title="Amostra E1 Daiane 2025 — rascunho (teste)",
        catalog=TEST_CATALOG,
        content=content,
        source_label="data/catalogs/fixtures/daiane-e1-rascunho/rascunho.json",
        reason="levar o rascunho da E1 ao fluxo de curadoria, sem aprovar",
    ).value


@pytest.mark.external_data
def test_real_draft_enters_curation_unchanged_and_only_as_draft(
    env: CurationEnv, daiane_draft: CatalogContent
) -> None:
    head = _import(env, daiane_draft)
    stored = env.curation.get_revision(head.draft.draft_id, 1)

    assert stored.content == daiane_draft
    assert head.content_sha256 == content_sha256(daiane_draft)
    lifecycles = {
        getattr(entity, "lifecycle")  # noqa: B009
        for kind, entity in stored.content.iter_entities()
        if hasattr(entity, "lifecycle")
    }
    assert lifecycles == {"draft"}


@pytest.mark.external_data
def test_area_forma_uses_keep_undetermined_carrier_and_writing_blocked(
    env: CurationEnv, daiane_draft: CatalogContent
) -> None:
    head = _import(env, daiane_draft)
    bindings = {b.id: b for b in env.curation.get_revision(head.draft.draft_id, 1).content.bindings}

    for binding_id in AREA_FORMA_BINDINGS:
        binding = bindings[binding_id]
        assert binding.field_name == "Area_Forma"
        assert binding.set_name == "EB_Orçamento"
        assert binding.carrier_kind == "property_or_quantity"
        assert binding.carrier_status == "pending_reconciliation"
        assert binding.ifc_type is None
        assert binding.scope == "unspecified"
        assert binding.write_enabled is False


@pytest.mark.external_data
def test_pending_items_and_unavailable_operations_are_visible(
    env: CurationEnv, daiane_draft: CatalogContent
) -> None:
    head = _import(env, daiane_draft)

    report = env.curation.validate_draft(head.draft.draft_id)

    pending = {(x.code, x.entity_id) for x in report.by_severity("pending")}
    assert ("decision.pending", AREA_FORMA_DECISION) in pending
    assert "capability.operation_unavailable" in {x.code for x in report.by_severity("warning")}
    carrier = {
        x.entity_id: x.severity for x in report.findings if x.code == "carrier.pending_proposal"
    }
    expected = "error" if PENDING_CARRIER_POLICY == "block" else "pending"
    assert carrier == dict.fromkeys(AREA_FORMA_BINDINGS, expected)


@pytest.mark.external_data
@pytest.mark.skipif(PENDING_CARRIER_POLICY != "block", reason="vale para a política B")
def test_under_policy_b_the_real_draft_cannot_reach_review(
    env: CurationEnv, daiane_draft: CatalogContent
) -> None:
    head = _import(env, daiane_draft)

    with pytest.raises(ValidationGateError, match=r"carrier\.pending_proposal"):
        env.curation.submit_for_review(
            _meta("cmd-sub-dai", env.curator),
            draft_id=head.draft.draft_id,
            revision=head.revision,
            content_sha256=head.content_sha256,
            reason="tentativa de submeter a amostra com portador pendente",
        )

    assert env.curation.get_draft(head.draft.draft_id).state == "editing"


@pytest.mark.external_data
def test_no_candidate_can_exist_without_approval(
    env: CurationEnv, daiane_draft: CatalogContent
) -> None:
    head = _import(env, daiane_draft)

    with pytest.raises(InvalidTransitionError):
        env.publication.prepare_release(
            _meta("cmd-prp-dai", env.curator),
            draft_id=head.draft.draft_id,
            revision=head.revision,
            content_sha256=head.content_sha256,
            version="0.1.0",
            terms=(ComponentTerms(component="conteúdo", terms="teste"),),
            reason="tentativa sem aprovação",
        )

    assert env.artifacts.staged_dirs() == ()


@pytest.mark.external_data
def test_enabling_writing_on_area_forma_is_refused_by_the_model(
    env: CurationEnv, daiane_draft: CatalogContent
) -> None:
    head = _import(env, daiane_draft)
    binding = next(b for b in daiane_draft.bindings if b.id == AREA_FORMA_BINDINGS[0])

    with pytest.raises(DraftPatchError):
        env.curation.edit_draft(
            _meta("cmd-edt-dai-1", env.curator),
            draft_id=head.draft.draft_id,
            expected_revision=1,
            patch=DraftPatch(
                operations=(
                    UpsertEntity(
                        op="upsert",
                        kind="bindings",
                        entity={**binding.model_dump(mode="json"), "write_enabled": True},
                    ),
                ),
                reason="tentativa de habilitar escrita",
            ),
        )

    assert env.curation.get_draft(head.draft.draft_id).current_revision == 1


@pytest.mark.external_data
def test_reconciling_the_carrier_while_the_decision_is_pending_is_flagged(
    env: CurationEnv, daiane_draft: CatalogContent
) -> None:
    head = _import(env, daiane_draft)
    binding = next(b for b in daiane_draft.bindings if b.id == AREA_FORMA_BINDINGS[0])
    reconciled = {
        **binding.model_dump(mode="json"),
        "carrier_kind": "quantity",
        "carrier_status": "approved",
        "ifc_type": "IfcQuantityArea",
    }

    env.curation.edit_draft(
        _meta("cmd-edt-dai-2", env.curator),
        draft_id=head.draft.draft_id,
        expected_revision=1,
        patch=DraftPatch(
            operations=(UpsertEntity(op="upsert", kind="bindings", entity=reconciled),),
            reason="escolher um portador sem evidência (deve ser sinalizado)",
        ),
    )

    report = env.curation.validate_draft(head.draft.draft_id)
    locked = {x.entity_id for x in report.findings if x.code == "decision.pending_locks_carrier"}
    assert locked == {AREA_FORMA_BINDINGS[0]}
    assert not report.passed
