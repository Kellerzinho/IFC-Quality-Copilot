"""Fachada E5 da área de trabalho do catálogo (M1-14) sobre os serviços reais.

Tudo roda numa SIMULAÇÃO sintética em pasta temporária (banco ``synthetic_test``):
catálogo, projeto, IFC/IDS e atores são rótulos de teste. Aprovações e publicações
feitas aqui são ensaio técnico, nunca revisão humana de conteúdo real.
"""

import uuid
from pathlib import Path

import pytest

from src.domain_catalog.curation_models import RequestedField
from src.domain_catalog.package import ComponentTerms
from src.domain_catalog.workspace import (
    CatalogWorkspace,
    open_components,
    scrub,
    translate,
)
from src.domain_catalog.workspace_models import (
    CatalogView,
    RowFilters,
    WorkspaceError,
    WorkspaceSession,
)
from src.domain_catalog.workspace_simulation import (
    SIM_B_CODIGO,
    SIM_B_METODO,
    SIM_CATALOG_ID,
    SIM_METODO,
    SIM_P_RECOVER,
    Simulation,
    create_simulation,
)

TERMS = (ComponentTerms(component="conteúdo", terms="sintético, sem terceiros"),)


@pytest.fixture
def sim(tmp_path: Path) -> Simulation:
    return create_simulation(tmp_path / "sim")


def _draft_view(sim: Simulation) -> CatalogView:
    return CatalogView(kind="draft", draft_id=sim.draft_id)


def _head(sim: Simulation) -> tuple[int, str]:
    (draft,) = [d for d in sim.workspace.list_drafts() if d.draft_id == sim.draft_id]
    return draft.revision, draft.content_sha256


def _add_column_usage(sim: Simulation, session: WorkspaceSession, **changes: object) -> None:
    revision, _ = _head(sim)
    data: dict[str, object] = {
        "command_id": sim.workspace.new_command_id(),
        "draft_id": sim.draft_id,
        "expected_revision": revision,
        "concept_id": SIM_METODO,
        "entity_classes": ["IfcColumn"],
        "include_subtypes": False,
        "schemas": ["IFC4"],
        "carrier_kind": "property",
        "set_name": "SIM_Conjunto",
        "set_kind": "custom",
        "field_name": "SIM_Metodo",
        "ifc_type": "IfcLabel",
        "scope": "occurrence",
        "evidence_policy_id": SIM_P_RECOVER,
        "reason": "mesmo conceito em pilares",
        **changes,
    }
    sim.workspace.add_usage(session, **data)  # type: ignore[arg-type]


def _publish(sim: Simulation, session: WorkspaceSession, version: str = "1.0.0") -> None:
    ws = sim.workspace
    revision, digest = _head(sim)
    ws.submit_for_review(
        session,
        command_id=ws.new_command_id(),
        draft_id=sim.draft_id,
        revision=revision,
        content_sha256=digest,
        reason="pronto para revisão",
    )
    ws.review(
        session,
        command_id=ws.new_command_id(),
        draft_id=sim.draft_id,
        revision=revision,
        content_sha256=digest,
        verdict="approve",
        justification="Conferência sintética de teste técnico.",
    )
    ws.prepare_release(
        session,
        command_id=ws.new_command_id(),
        draft_id=sim.draft_id,
        revision=revision,
        content_sha256=digest,
        version=version,
        terms=TERMS,
        reason="preparar candidato",
    )
    (draft,) = [d for d in ws.list_drafts() if d.draft_id == sim.draft_id]
    assert draft.candidate_id is not None
    candidate = ws.candidate(draft.candidate_id)
    ws.publish(
        session,
        command_id=ws.new_command_id(),
        candidate_id=candidate.candidate_id,
        version=candidate.version,
        manifest_sha256=candidate.manifest_sha256,
        justification="Publicação simulada de teste.",
    )


def test_simulation_store_is_synthetic_and_modes_cannot_be_crossed(tmp_path: Path) -> None:
    sim = create_simulation(tmp_path / "sim")
    assert sim.workspace.mode == "simulation"
    assert sim.workspace.components.store.purpose == "synthetic_test"
    with pytest.raises(WorkspaceError) as crossed:
        CatalogWorkspace(sim.workspace.components, mode="operational")
    assert crossed.value.code == "purpose_mismatch"
    operational = open_components(tmp_path / "op", purpose="operational")
    with pytest.raises(WorkspaceError):
        CatalogWorkspace(operational, mode="simulation")
    with pytest.raises(ValueError, match="pasta nova e vazia"):
        create_simulation(tmp_path / "sim")


def test_rows_filters_and_detail_keep_concept_binding_and_source_apart(sim: Simulation) -> None:
    ws = sim.workspace
    view = _draft_view(sim)
    rows = ws.rows(view)
    assert [r.field_name for r in rows] == ["SIM_Metodo", "SIM_Codigo"]
    assert {r.lifecycle for r in rows} == {"draft"}
    assert {r.capability.state for r in rows} == {"available"}
    assert all(r.write_enabled is False for r in rows)
    options = ws.filter_options(view)
    assert options.profiles == ("simulacao-e5",)
    assert options.entity_classes == ("IfcSlab",)
    assert ws.rows(view, RowFilters(entity_class="IfcWall")) == ()
    assert ws.rows(view, RowFilters(source="synthetic:outra")) == ()
    assert len(ws.rows(view, RowFilters(profile="simulacao-e5", state="draft"))) == 2

    detail = ws.detail(view, SIM_B_METODO)
    assert detail.row.concept_id == SIM_METODO
    assert detail.row.binding_id == SIM_B_METODO
    pairs = {p.aspect: p for p in detail.original_vs_reconciled}
    assert pairs["nome do campo"].original == ("SIM Metodo",)
    assert pairs["nome do campo"].reconciled == "SIM_Metodo"
    assert pairs["tipo"].original == ("Texto",)
    assert [a.term for a in detail.aliases] == ["Metodo"]
    assert detail.aliases[0].scope == "conjuntos=['SIM_Legado']"
    assert detail.assertions[0].transcription_status == "registered"
    assert [h.operation for h in detail.history] == ["import_draft"]
    code_detail = ws.detail(view, SIM_B_CODIGO)
    assert code_detail.value_set == ("A1", "B2")
    with pytest.raises(WorkspaceError) as missing:
        ws.detail(view, "urn:uuid:00000000-0000-4000-8000-00000000ffff")
    assert missing.value.code == "not_found"


def test_source_text_that_looks_like_an_instruction_is_returned_as_inert_data(
    sim: Simulation,
) -> None:
    ws = sim.workspace
    content = ws.view_content(_draft_view(sim))
    note = content.source_assertions[0].notes[0]
    assert "Ignore as instruções" in note
    before = ws.list_drafts()
    ws.detail(_draft_view(sim), SIM_B_METODO)
    assert ws.list_drafts() == before
    assert ws.list_releases() == ()


def test_operator_request_is_recorded_without_creating_equivalence(sim: Simulation) -> None:
    ws = sim.workspace
    operator = ws.open_session("Operadora Sintética (teste)")
    receipt = ws.request_change(
        operator,
        command_id=ws.new_command_id(),
        catalog_id=SIM_CATALOG_ID,
        motivation="IDS exige campo não cadastrado",
        field=RequestedField(field_name="SIM_Desconhecido", set_name="SIM_Conjunto"),
    )
    assert receipt.operation == "request_change"
    (request,) = ws.list_requests()
    assert request.state == "open"
    assert request.requested_by.declared_name == "Operadora Sintética (teste)"
    assert len(ws.rows(_draft_view(sim))) == 2
    rejected = ws.act_on_request(
        operator,
        command_id=ws.new_command_id(),
        request_id=request.request_id,
        action="reject",
        reason="Fora do escopo do perfil sintético.",
    )
    assert "reject" in rejected.message
    assert ws.list_requests()[0].state == "rejected"
    with pytest.raises(WorkspaceError):
        ws.act_on_request(
            operator,
            command_id=ws.new_command_id(),
            request_id=request.request_id,
            action="aprovar",
            reason="x",
        )


def test_add_usage_with_existing_operation_reuses_the_concept_without_json(
    sim: Simulation,
) -> None:
    ws = sim.workspace
    curator = ws.open_session("Pessoa Curadora Sintética (teste)")
    _add_column_usage(sim, curator)
    rows = ws.rows(_draft_view(sim))
    column = [r for r in rows if r.entity_classes == ("IfcColumn",)]
    assert len(column) == 1
    assert column[0].concept_id == SIM_METODO
    assert column[0].concept_shared_by == 2
    assert column[0].capability.state == "available"
    assert column[0].write_enabled is False
    assert len({r.concept_id for r in rows}) == 2
    report = ws.validation(sim.draft_id)
    assert report.errors == 0
    assert any(
        "pilares" in h.reason
        for h in ws.detail(_draft_view(sim), column[0].binding_id).history
        if h.reason
    )


def test_unavailable_operation_is_refused_and_points_to_a_request(sim: Simulation) -> None:
    ws = sim.workspace
    curator = ws.open_session("Pessoa Curadora Sintética (teste)")
    before = _head(sim)
    with pytest.raises(WorkspaceError) as refused:
        _add_column_usage(
            sim,
            curator,
            evidence_policy_id=None,
            operation_id="calcular_area_de_forma",
        )
    assert refused.value.code == "operation_unavailable"
    assert "solicitação" in refused.value.message
    assert _head(sim) == before
    assert [c.operation_id for c in ws.operations()] == [
        "normalize_code_nfc_trim",
        "recover_exact_property",
    ]
    with pytest.raises(WorkspaceError):
        _add_column_usage(sim, curator, operation_id="recover_exact_property")


def test_new_policy_on_registered_operation_is_validated_by_the_service(
    sim: Simulation,
) -> None:
    ws = sim.workspace
    curator = ws.open_session("Pessoa Curadora Sintética (teste)")
    _add_column_usage(
        sim,
        curator,
        evidence_policy_id=None,
        operation_id="recover_exact_property",
        channels=["P", "T"],
    )
    report = ws.validation(sim.draft_id)
    duplicates = [i for i in report.issues if i.code == "identity.unreviewed_duplicate"]
    assert duplicates
    assert duplicates[0].entity_kind == "evidence_policies"
    revision, digest = _head(sim)
    with pytest.raises(WorkspaceError) as gate:
        ws.submit_for_review(
            curator,
            command_id=ws.new_command_id(),
            draft_id=sim.draft_id,
            revision=revision,
            content_sha256=digest,
            reason="tentar submeter",
        )
    assert gate.value.code == "validation_failed"


def test_invalid_field_returns_field_issues_and_nothing_is_saved(sim: Simulation) -> None:
    ws = sim.workspace
    curator = ws.open_session("Pessoa Curadora Sintética (teste)")
    before = _head(sim)
    with pytest.raises(WorkspaceError) as invalid:
        _add_column_usage(sim, curator, entity_classes=["Pilar"])
    assert invalid.value.code == "invalid_input"
    assert invalid.value.issues
    assert invalid.value.keep_input is True
    with pytest.raises(WorkspaceError) as no_kind:
        _add_column_usage(sim, curator, set_kind=None)
    assert any("set_kind" in i.message for i in no_kind.value.issues)
    assert _head(sim) == before


def test_duplicate_row_keeps_the_concept_and_requires_identity_review(sim: Simulation) -> None:
    ws = sim.workspace
    curator = ws.open_session("Pessoa Curadora Sintética (teste)")
    revision, _ = _head(sim)
    ws.duplicate_usage(
        curator,
        command_id=ws.new_command_id(),
        draft_id=sim.draft_id,
        expected_revision=revision,
        binding_id=SIM_B_METODO,
        reason="duplicar linha",
    )
    rows = ws.rows(_draft_view(sim))
    copies = [r for r in rows if r.concept_id == SIM_METODO]
    assert len(copies) == 2
    assert len({r.concept_id for r in rows}) == 2
    report = ws.validation(sim.draft_id)
    assert any(
        i.code == "identity.unreviewed_duplicate" and i.entity_kind == "bindings"
        for i in report.issues
    )
    new_id = next(r.binding_id for r in copies if r.binding_id != SIM_B_METODO)
    revision, _ = _head(sim)
    ws.edit_entity(
        curator,
        command_id=ws.new_command_id(),
        draft_id=sim.draft_id,
        expected_revision=revision,
        kind="bindings",
        entity_id=new_id,
        changes={"field_name": "SIM_Metodo_Pilar"},
        reason="revisar identidade da cópia",
    )
    assert not any(
        i.code == "identity.unreviewed_duplicate" and i.entity_kind == "bindings"
        for i in ws.validation(sim.draft_id).issues
    )


def test_derived_fields_and_non_editable_kinds_are_refused(sim: Simulation) -> None:
    ws = sim.workspace
    curator = ws.open_session("Pessoa Curadora Sintética (teste)")
    revision, _ = _head(sim)
    common = {
        "command_id": ws.new_command_id(),
        "draft_id": sim.draft_id,
        "expected_revision": revision,
        "reason": "x",
    }
    with pytest.raises(WorkspaceError) as derived:
        ws.edit_entity(
            curator,
            kind="bindings",
            entity_id=SIM_B_METODO,
            changes={"lifecycle": "approved"},
            **common,  # type: ignore[arg-type]
        )
    assert derived.value.code == "derived_field"
    assert derived.value.issues[0].field == "lifecycle"
    with pytest.raises(WorkspaceError):
        ws.edit_entity(
            curator,
            kind="source_assertions",
            entity_id="synthetic:simulacao-e5-linha-1",
            changes={"target_literal": "x"},
            **common,  # type: ignore[arg-type]
        )
    with pytest.raises(WorkspaceError) as absent:
        ws.edit_entity(
            curator,
            kind="bindings",
            entity_id="urn:uuid:00000000-0000-4000-8000-00000000ffff",
            changes={"field_name": "x"},
            **common,  # type: ignore[arg-type]
        )
    assert absent.value.code == "not_found"


def test_revision_conflict_preserves_the_users_edit_and_reports_current(
    sim: Simulation,
) -> None:
    ws = sim.workspace
    first = ws.open_session("Pessoa A Sintética")
    second = ws.open_session("Pessoa B Sintética")
    revision, _ = _head(sim)
    ws.edit_entity(
        first,
        command_id=ws.new_command_id(),
        draft_id=sim.draft_id,
        expected_revision=revision,
        kind="bindings",
        entity_id=SIM_B_CODIGO,
        changes={"notes": "nota da pessoa A"},
        reason="editar A",
    )
    with pytest.raises(WorkspaceError) as conflict:
        ws.edit_entity(
            second,
            command_id=ws.new_command_id(),
            draft_id=sim.draft_id,
            expected_revision=revision,
            kind="bindings",
            entity_id=SIM_B_METODO,
            changes={"notes": "nota da pessoa B"},
            reason="editar B",
        )
    assert conflict.value.code == "revision_conflict"
    assert conflict.value.keep_input is True
    assert _head(sim)[0] == revision + 1


def test_stale_revision_on_the_service_is_a_revision_conflict(sim: Simulation) -> None:
    ws = sim.workspace
    curator = ws.open_session("Pessoa Curadora Sintética")
    _add_column_usage(sim, curator)
    with pytest.raises(WorkspaceError) as conflict:
        ws.duplicate_usage(
            curator,
            command_id=ws.new_command_id(),
            draft_id=sim.draft_id,
            expected_revision=1,
            binding_id=SIM_B_METODO,
            reason="duplicar sobre revisão antiga",
        )
    assert conflict.value.code == "revision_conflict"
    assert conflict.value.current_revision == 2
    assert "preservada" in conflict.value.message


def test_repeating_a_command_key_replays_and_a_different_payload_conflicts(
    sim: Simulation,
) -> None:
    ws = sim.workspace
    curator = ws.open_session("Pessoa Curadora Sintética")
    key = ws.new_command_id()
    revision, _ = _head(sim)
    data = {
        "command_id": key,
        "draft_id": sim.draft_id,
        "expected_revision": revision,
        "binding_id": SIM_B_METODO,
        "reason": "duplicar",
    }
    first = ws.duplicate_usage(curator, **data)  # type: ignore[arg-type]
    assert first.replayed is False
    assert ws.command_status(key) == "completed"
    with pytest.raises(WorkspaceError) as conflict:
        ws.duplicate_usage(curator, **{**data, "reason": "outro motivo"})  # type: ignore[arg-type]
    assert conflict.value.code == "idempotency_conflict"
    assert ws.command_status(ws.new_command_id()) == "desconhecido"
    assert len(ws.revisions(sim.draft_id)) == 2


def test_review_rejection_and_request_changes_keep_history_and_nothing_publishes(
    sim: Simulation,
) -> None:
    ws = sim.workspace
    curator = ws.open_session("Pessoa Curadora Sintética")
    revision, digest = _head(sim)
    ws.submit_for_review(
        curator,
        command_id=ws.new_command_id(),
        draft_id=sim.draft_id,
        revision=revision,
        content_sha256=digest,
        reason="submeter",
    )
    with pytest.raises(WorkspaceError) as stale:
        ws.review(
            curator,
            command_id=ws.new_command_id(),
            draft_id=sim.draft_id,
            revision=revision,
            content_sha256="0" * 64,
            verdict="approve",
            justification="hash errado",
        )
    assert stale.value.code == "content_hash_mismatch"
    ws.review(
        curator,
        command_id=ws.new_command_id(),
        draft_id=sim.draft_id,
        revision=revision,
        content_sha256=digest,
        verdict="request_changes",
        justification="Revise a aplicabilidade do uso sintético.",
    )
    assert ws.reviews(sim.draft_id)[0].startswith("r1 request_changes")
    assert ws.revision_diff(sim.draft_id)[0].startswith("+ ")
    assert ws.list_releases() == ()


def test_service_authorization_is_not_a_hidden_button(sim: Simulation) -> None:
    ws = sim.workspace
    anonymous = ws.open_session("   ")
    assert anonymous.declared_name is None
    revision, digest = _head(sim)
    ws.submit_for_review(
        anonymous,
        command_id=ws.new_command_id(),
        draft_id=sim.draft_id,
        revision=revision,
        content_sha256=digest,
        reason="submeter",
    )
    with pytest.raises(WorkspaceError) as refused:
        ws.review(
            anonymous,
            command_id=ws.new_command_id(),
            draft_id=sim.draft_id,
            revision=revision,
            content_sha256=digest,
            verdict="approve",
            justification="sem responsável declarado",
        )
    assert refused.value.code == "actor_not_allowed"

    importer = ws.components.actors.register(actor_kind="service", declared_name=None)
    forged = WorkspaceSession(
        session_id=str(uuid.uuid4()),
        actor_context_id=importer.actor_context_id,
        declared_name=None,
        mode="simulation",
    )
    with pytest.raises(WorkspaceError) as unknown:
        ws.review(
            forged,
            command_id=ws.new_command_id(),
            draft_id=sim.draft_id,
            revision=revision,
            content_sha256=digest,
            verdict="approve",
            justification="sessão forjada",
        )
    assert unknown.value.code == "session_unknown"
    issued = ws.open_session("Pessoa Sintética")
    tampered = issued.model_copy(update={"actor_context_id": importer.actor_context_id})
    with pytest.raises(WorkspaceError) as swapped:
        ws.review(
            tampered,
            command_id=ws.new_command_id(),
            draft_id=sim.draft_id,
            revision=revision,
            content_sha256=digest,
            verdict="approve",
            justification="ator trocado",
        )
    assert swapped.value.code == "session_unknown"


def test_simulated_publication_requires_the_exact_hash_and_never_moves_a_pin(
    sim: Simulation,
) -> None:
    ws = sim.workspace
    curator = ws.open_session("Pessoa Curadora Sintética")
    revision, digest = _head(sim)
    ws.submit_for_review(
        curator,
        command_id=ws.new_command_id(),
        draft_id=sim.draft_id,
        revision=revision,
        content_sha256=digest,
        reason="submeter",
    )
    ws.review(
        curator,
        command_id=ws.new_command_id(),
        draft_id=sim.draft_id,
        revision=revision,
        content_sha256=digest,
        verdict="approve",
        justification="Conferência sintética.",
    )
    ws.prepare_release(
        curator,
        command_id=ws.new_command_id(),
        draft_id=sim.draft_id,
        revision=revision,
        content_sha256=digest,
        version="1.0.0",
        terms=TERMS,
        reason="preparar",
    )
    (draft,) = ws.list_drafts()
    assert draft.candidate_id is not None
    candidate = ws.candidate(draft.candidate_id)
    assert candidate.state == "prepared"
    with pytest.raises(WorkspaceError) as mismatch:
        ws.publish(
            curator,
            command_id=ws.new_command_id(),
            candidate_id=candidate.candidate_id,
            version=candidate.version,
            manifest_sha256="f" * 64,
            justification="hash errado",
        )
    assert mismatch.value.code == "candidate_mismatch"
    key = ws.new_command_id()
    published = ws.publish(
        curator,
        command_id=key,
        candidate_id=candidate.candidate_id,
        version=candidate.version,
        manifest_sha256=candidate.manifest_sha256,
        justification="Publicação simulada.",
    )
    again = ws.publish(
        curator,
        command_id=key,
        candidate_id=candidate.candidate_id,
        version=candidate.version,
        manifest_sha256=candidate.manifest_sha256,
        justification="Publicação simulada.",
    )
    assert (published.replayed, again.replayed) == (False, True)
    assert "idempotente" in again.message
    (release,) = ws.list_releases()
    assert release.manifest_sha256 == candidate.manifest_sha256
    assert ws.pin_view(sim.project_id).catalog is None
    rows = ws.rows(CatalogView(kind="release", release=release))
    assert {r.lifecycle for r in rows} == {"approved"}
    history = ws.detail(CatalogView(kind="release", release=release), SIM_B_METODO).history
    assert history[-1].operation == "publish"
    assert ws.publication_inspection() == ()


def test_publication_in_progress_and_base_superseded_have_useful_messages(
    sim: Simulation, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = sim.workspace
    curator = ws.open_session("Pessoa Curadora Sintética")
    _publish(sim, curator)
    (release,) = ws.list_releases()
    for title in ("Rascunho X", "Rascunho Y"):
        ws.create_draft(
            curator,
            command_id=ws.new_command_id(),
            title=title,
            reason="atualizar",
            base_release=release,
        )
    drafts = [d for d in ws.list_drafts() if d.title in ("Rascunho X", "Rascunho Y")]
    for index, draft in enumerate(drafts):
        ws.edit_entity(
            curator,
            command_id=ws.new_command_id(),
            draft_id=draft.draft_id,
            expected_revision=draft.revision,
            kind="bindings",
            entity_id=SIM_B_CODIGO,
            changes={"notes": f"nota {index}"},
            reason="nota",
        )
    heads = [d for d in ws.list_drafts() if d.title in ("Rascunho X", "Rascunho Y")]
    candidates = []
    for index, head in enumerate(heads):
        for action in ("submit", "review", "prepare"):
            key = ws.new_command_id()
            if action == "submit":
                ws.submit_for_review(
                    curator,
                    command_id=key,
                    draft_id=head.draft_id,
                    revision=head.revision,
                    content_sha256=head.content_sha256,
                    reason="x",
                )
            elif action == "review":
                ws.review(
                    curator,
                    command_id=key,
                    draft_id=head.draft_id,
                    revision=head.revision,
                    content_sha256=head.content_sha256,
                    verdict="approve",
                    justification="Conferência sintética.",
                )
            else:
                ws.prepare_release(
                    curator,
                    command_id=key,
                    draft_id=head.draft_id,
                    revision=head.revision,
                    content_sha256=head.content_sha256,
                    version=f"1.{index + 1}.0",
                    terms=TERMS,
                    reason="x",
                )
        (found,) = [d for d in ws.list_drafts() if d.draft_id == head.draft_id]
        assert found.candidate_id is not None
        candidates.append(ws.candidate(found.candidate_id))

    releases = ws.components.releases
    real_promote = releases.promote

    def interrupted(*args: object, **kwargs: object) -> Path:
        raise OSError(5, r"falha em C:\Users\alguem\segredo\pasta")

    monkeypatch.setattr(releases, "promote", interrupted)
    first_key = ws.new_command_id()
    with pytest.raises(WorkspaceError) as incomplete:
        ws.publish(
            curator,
            command_id=first_key,
            candidate_id=candidates[0].candidate_id,
            version=candidates[0].version,
            manifest_sha256=candidates[0].manifest_sha256,
            justification="Publicação simulada.",
        )
    assert incomplete.value.code == "publication_incomplete"
    assert incomplete.value.retry_same_key is True
    assert "segredo" not in incomplete.value.message
    assert ws.publication_inspection()[0].startswith("intenção pendente")
    with pytest.raises(WorkspaceError) as busy:
        ws.publish(
            curator,
            command_id=ws.new_command_id(),
            candidate_id=candidates[1].candidate_id,
            version=candidates[1].version,
            manifest_sha256=candidates[1].manifest_sha256,
            justification="Publicação simulada.",
        )
    assert busy.value.code == "publication_in_progress"
    assert "Retome" in busy.value.message

    monkeypatch.setattr(releases, "promote", real_promote)
    ws.publish(
        curator,
        command_id=first_key,
        candidate_id=candidates[0].candidate_id,
        version=candidates[0].version,
        manifest_sha256=candidates[0].manifest_sha256,
        justification="Publicação simulada.",
    )
    with pytest.raises(WorkspaceError) as superseded:
        ws.publish(
            curator,
            command_id=ws.new_command_id(),
            candidate_id=candidates[1].candidate_id,
            version=candidates[1].version,
            manifest_sha256=candidates[1].manifest_sha256,
            justification="Publicação simulada.",
        )
    assert superseded.value.code == "base_superseded"
    assert "release atual" in superseded.value.message


def test_pin_preview_adoption_and_rollback_are_explicit_and_traceable(
    sim: Simulation,
) -> None:
    ws = sim.workspace
    curator = ws.open_session("Pessoa Curadora Sintética")
    _publish(sim, curator)
    (r1,) = ws.list_releases()
    assert ws.pin_view(sim.project_id).catalog is None

    preview = ws.preview_adoption(
        curator, project_id=sim.project_id, target=r1, intent="initial", reason="adotar r1"
    )
    assert preview.diff_absent_reason == "no_previous_catalog"
    assert ws.pin_view(sim.project_id).pin_revision == 0
    with pytest.raises(WorkspaceError) as wrong:
        ws.apply_adoption(
            curator,
            command_id=str(uuid.uuid4()),
            project_id=sim.project_id,
            plan_id=preview.plan_id,
            plan_sha256="0" * 64,
        )
    assert wrong.value.code.startswith("adoption_")
    applied = ws.apply_adoption(
        curator,
        command_id=str(uuid.uuid4()),
        project_id=sim.project_id,
        plan_id=preview.plan_id,
        plan_sha256=preview.plan_sha256,
    )
    assert applied.revision == 1
    pin = ws.pin_view(sim.project_id)
    assert pin.catalog == r1
    assert len(pin.history) == 1

    ws.create_draft(
        curator,
        command_id=ws.new_command_id(),
        title="Atualização",
        reason="r2",
        base_release=r1,
    )
    draft = next(d for d in ws.list_drafts() if d.title == "Atualização")
    ws.edit_entity(
        curator,
        command_id=ws.new_command_id(),
        draft_id=draft.draft_id,
        expected_revision=draft.revision,
        kind="aliases",
        entity_id="urn:uuid:00000000-0000-4000-8000-0000000e5009",
        changes={"scope": {"set_names": ["SIM_Antigo"]}},
        reason="corrigir escopo do alias",
    )
    sim2 = Simulation(
        workspace=ws, project_id=sim.project_id, draft_id=draft.draft_id, base=sim.base
    )
    _publish(sim2, curator, "1.1.0")
    r2 = ws.list_releases()[-1]
    update = ws.preview_adoption(
        curator, project_id=sim.project_id, target=r2, intent="update", reason="r2"
    )
    assert update.old_catalog == r1
    assert any("aliases" in line for line in update.diff_lines)
    ws.apply_adoption(
        curator,
        command_id=str(uuid.uuid4()),
        project_id=sim.project_id,
        plan_id=update.plan_id,
        plan_sha256=update.plan_sha256,
    )
    back = ws.preview_adoption(
        curator, project_id=sim.project_id, target=r1, intent="rollback", reason="voltar"
    )
    ws.apply_adoption(
        curator,
        command_id=str(uuid.uuid4()),
        project_id=sim.project_id,
        plan_id=back.plan_id,
        plan_sha256=back.plan_sha256,
    )
    pin = ws.pin_view(sim.project_id)
    assert pin.pin_revision == 3
    assert pin.catalog == r1
    assert len(pin.history) == 3
    analyses = ws.list_analyses(sim.project_id)
    assert [a[2] for a in analyses] == [1, 2, 3]
    assert ws.list_projects()[0][0] == sim.project_id


def test_analysis_view_separates_ids_mapping_and_evidence(sim: Simulation) -> None:
    pytest.importorskip("ifctester", reason="extra e3 não instalado (ifctester==0.8.5)")
    ws = sim.workspace
    curator = ws.open_session("Pessoa Curadora Sintética")
    _publish(sim, curator)
    (release,) = ws.list_releases()
    preview = ws.preview_adoption(
        curator, project_id=sim.project_id, target=release, intent="initial", reason="adotar"
    )
    ws.apply_adoption(
        curator,
        command_id=str(uuid.uuid4()),
        project_id=sim.project_id,
        plan_id=preview.plan_id,
        plan_sha256=preview.plan_sha256,
    )
    (queued,) = ws.list_analyses(sim.project_id)
    queued_view = ws.analysis_view(queued[0])
    assert queued_view.rows == ()
    assert "sem diagnóstico" in queued_view.limitations[0]
    (line,) = ws.execute_queued_analyses(curator, sim.project_id)
    assert "completed" in line
    assert ws.execute_queued_analyses(curator, sim.project_id) == ()
    view = ws.analysis_view(queued[0])
    assert view.catalog == release
    assert len(view.rows) == 4
    assert {r.ids_state for r in view.rows} == {"non_compliant"}
    assert {r.mapping_state for r in view.rows} == {"resolved"}
    assert {r.evidence_state for r in view.rows} == {"proposed", "abstained"}
    proposed = [r for r in view.rows if r.evidence_state == "proposed"]
    assert len(proposed) == 1
    assert "requer revisão humana" in (proposed[0].evidence_detail or "")
    assert proposed[0].expected.startswith("SIM_Conjunto.SIM_Metodo")
    assert proposed[0].found.startswith("IfcTester:")
    by_requirement = ws.analysis_view(queued[0], group_by="requirement")
    assert [r.requirement for r in by_requirement.rows] == sorted(
        r.requirement for r in by_requirement.rows
    )


def test_translate_never_exposes_paths_or_stack_traces() -> None:
    hidden = translate(RuntimeError(r"C:\Users\pessoa\projeto\segredo.ifc"))
    assert hidden.code == "unexpected"
    assert "segredo" not in hidden.message
    for text in (
        r"erro em C:\Users\x\a.json e /home/y/b.json",
        r"falha em C:\Users\alguem\ProjetoSintetico\Testes\x.json: erro",
        r"ausente em \\servidor\pasta com espaço\r\1.0.0",
    ):
        cleaned = scrub(text)
        assert "<caminho omitido>" in cleaned
        assert not any(part in cleaned for part in ("Users", "Projetos", "Pesquisa", "servidor"))
    assert translate(ValueError(r"ruim: D:\dados\x.db")).message == "ruim: <caminho omitido>"
    same = WorkspaceError("x", "y")
    assert translate(same) is same


def test_dangling_concept_reference_is_shown_not_crashed_and_can_be_withdrawn(
    sim: Simulation,
) -> None:
    ws = sim.workspace
    person = ws.open_session("Pessoa Sintética")
    revision, _ = _head(sim)
    ghost = "urn:uuid:00000000-0000-4000-8000-00000000dead"
    ws.edit_entity(
        person,
        command_id=ws.new_command_id(),
        draft_id=sim.draft_id,
        expected_revision=revision,
        kind="bindings",
        entity_id=SIM_B_CODIGO,
        changes={"concept_id": ghost},
        reason="referência pendente sintética",
    )
    rows = {r.binding_id: r for r in ws.rows(_draft_view(sim))}
    assert rows[SIM_B_CODIGO].concept_code.startswith("(referência ausente")
    assert ws.filter_options(_draft_view(sim)).entity_classes == ("IfcSlab",)
    with pytest.raises(WorkspaceError) as dangling:
        ws.detail(_draft_view(sim), SIM_B_CODIGO)
    assert dangling.value.code == "dangling_reference"
    assert ws.validation(sim.draft_id).errors >= 1
    revision, _ = _head(sim)
    ws.withdraw_proposal(
        person,
        command_id=ws.new_command_id(),
        draft_id=sim.draft_id,
        expected_revision=revision,
        kind="bindings",
        entity_id=SIM_B_CODIGO,
        reason="retirar proposta inválida",
    )
    assert SIM_B_CODIGO not in {r.binding_id for r in ws.rows(_draft_view(sim))}


def test_policy_edit_to_an_unimplemented_operation_is_refused(sim: Simulation) -> None:
    ws = sim.workspace
    person = ws.open_session("Pessoa Sintética")
    revision, _ = _head(sim)
    with pytest.raises(WorkspaceError) as refused:
        ws.edit_entity(
            person,
            command_id=ws.new_command_id(),
            draft_id=sim.draft_id,
            expected_revision=revision,
            kind="evidence_policies",
            entity_id=SIM_P_RECOVER,
            changes={"operation_id": "calcular_area_de_forma"},
            reason="trocar operação",
        )
    assert refused.value.code == "operation_unavailable"
    assert _head(sim)[0] == revision


def test_adoption_replay_and_invalid_identifiers_are_reported_clearly(sim: Simulation) -> None:
    ws = sim.workspace
    curator = ws.open_session("Pessoa Curadora Sintética")
    _publish(sim, curator)
    (release,) = ws.list_releases()
    preview = ws.preview_adoption(
        curator, project_id=sim.project_id, target=release, intent="initial", reason="x"
    )
    key = str(uuid.uuid4())
    data = {
        "command_id": key,
        "project_id": sim.project_id,
        "plan_id": preview.plan_id,
        "plan_sha256": preview.plan_sha256,
    }
    first = ws.apply_adoption(curator, **data)
    again = ws.apply_adoption(curator, **data)
    assert (first.replayed, again.replayed) == (False, True)
    assert "idempotente" in again.message
    assert ws.pin_view(sim.project_id).pin_revision == 1
    for call in (
        lambda: ws.pin_view("não-é-uuid"),
        lambda: ws.list_analyses("x"),
        lambda: ws.analysis_view("x"),
        lambda: ws.apply_adoption(curator, **{**data, "command_id": "x"}),
    ):
        with pytest.raises(WorkspaceError) as invalid:
            call()
        assert invalid.value.code == "invalid_input"
    with pytest.raises(WorkspaceError) as anonymous:
        ws.execute_queued_analyses(
            WorkspaceSession(
                session_id="forjada",
                actor_context_id=curator.actor_context_id,
                declared_name=None,
                mode="simulation",
            ),
            sim.project_id,
        )
    assert anonymous.value.code == "session_unknown"


def test_pending_intent_ids_are_exact_and_resumable(
    sim: Simulation, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = sim.workspace
    curator = ws.open_session("Pessoa Curadora Sintética")
    releases = ws.components.releases
    real_promote = releases.promote

    def interrupted(*args: object, **kwargs: object) -> Path:
        raise OSError(5, "falha simulada")

    monkeypatch.setattr(releases, "promote", interrupted)
    with pytest.raises(WorkspaceError):
        _publish(sim, curator)
    ((intent_id, version),) = ws.pending_intents()
    assert intent_id.startswith("urn:uuid:")
    assert version == "1.0.0"
    monkeypatch.setattr(releases, "promote", real_promote)
    ws.resume_publication(
        curator, command_id=ws.new_command_id(), intent_id=intent_id, reason="retomar"
    )
    assert ws.pending_intents() == ()
    assert [r.version for r in ws.list_releases()] == ["1.0.0"]


def test_scrub_omits_whole_paths_under_known_roots_and_with_spaces() -> None:
    import tempfile

    roots = [
        str(Path.home() / "Documents" / "area secreta" / "db" / "operations.sqlite3"),
        str(Path(tempfile.gettempdir()) / "pasta" / "modelo final.ifc"),
        str(Path(__file__).resolve().parents[2] / "data" / "catalogs" / "x.json"),
    ]
    for path in roots:
        cleaned = scrub(f"[not_found] release ausente em {path}")
        assert cleaned == "[not_found] release ausente em <caminho omitido>"
    assert scrub("ok: /home/pessoa/modelo final.ifc").endswith("<caminho omitido>")
    assert scrub("[integrity] bindings.json difere do manifesto") == (
        "[integrity] bindings.json difere do manifesto"
    )


def test_policy_version_edit_and_existing_policy_are_checked_against_the_registry(
    sim: Simulation,
) -> None:
    ws = sim.workspace
    person = ws.open_session("Pessoa Sintética")
    revision, _ = _head(sim)
    with pytest.raises(WorkspaceError) as version:
        ws.edit_entity(
            person,
            command_id=ws.new_command_id(),
            draft_id=sim.draft_id,
            expected_revision=revision,
            kind="evidence_policies",
            entity_id=SIM_P_RECOVER,
            changes={"operation_version": "9.9.9"},
            reason="versão inexistente",
        )
    assert version.value.code == "operation_unavailable"
    with pytest.raises(WorkspaceError) as missing:
        _add_column_usage(
            sim, person, evidence_policy_id="urn:uuid:00000000-0000-4000-8000-00000000beef"
        )
    assert missing.value.code == "not_found"
    assert _head(sim)[0] == revision


def test_scrub_does_not_mangle_urls() -> None:
    assert scrub("ver http://exemplo.invalido/a") == "ver http://exemplo.invalido/a"


@pytest.mark.parametrize("action", ["add_existing", "add_new_policy", "duplicate"])
def test_creation_commands_replay_exact_payload_after_response_loss(
    sim: Simulation, action: str
) -> None:
    ws = sim.workspace
    person = ws.open_session("Pessoa Sintética")
    key = ws.new_command_id()
    revision, _ = _head(sim)
    if action == "duplicate":

        def run(reason: str = "replay sintético"):
            return ws.duplicate_usage(
                person,
                command_id=key,
                draft_id=sim.draft_id,
                expected_revision=revision,
                binding_id=SIM_B_METODO,
                reason=reason,
            )
    else:
        options = (
            {"operation_id": "exact_property_read", "operation_version": None}
            if action == "add_new_policy"
            else {"evidence_policy_id": SIM_P_RECOVER}
        )
        if action == "add_new_policy":
            policy = ws.view_content(_draft_view(sim)).evidence_policies[0]
            options = {
                "operation_id": policy.operation_id,
                "operation_version": policy.operation_version,
            }

        def run(reason: str = "replay sintético"):
            return ws.add_usage(
                person,
                command_id=key,
                draft_id=sim.draft_id,
                expected_revision=revision,
                concept_id=SIM_METODO,
                entity_classes=["IfcColumn"],
                include_subtypes=False,
                schemas=["IFC4"],
                carrier_kind="property",
                set_name="SIM_Conjunto",
                set_kind="custom",
                field_name="SIM_Metodo",
                ifc_type="IfcLabel",
                scope="occurrence",
                reason=reason,
                **options,
            )

    first = run()
    after = ws.view_content(_draft_view(sim))
    again = run()
    assert (first.replayed, again.replayed) == (False, True)
    assert _head(sim)[0] == revision + 1
    assert ws.view_content(_draft_view(sim)) == after
    with pytest.raises(WorkspaceError) as changed:
        run("outro conteúdo")
    assert changed.value.code == "idempotency_conflict"
