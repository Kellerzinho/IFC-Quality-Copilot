"""Autoria e importação E5 em armazenamento sintético isolado, sem aceite real."""

from pathlib import Path

import pytest

from src.domain_catalog import schema
from src.domain_catalog.canonical import canonical_json_bytes
from src.domain_catalog.workspace import CatalogWorkspace, open_components
from src.domain_catalog.workspace_models import CatalogView, WorkspaceError, WorkspaceSession
from src.domain_catalog.workspace_simulation import create_simulation


def test_empty_workspace_can_start_import_and_replay_without_publication(tmp_path: Path) -> None:
    ws = CatalogWorkspace(
        open_components(tmp_path / "empty", purpose="synthetic_test"), mode="simulation"
    )
    person = ws.open_session("Pessoa sintética")
    args = dict(
        command_id=ws.new_command_id(),
        name="Catálogo sintético",
        namespace="synthetic",
        maintainer="Teste",
        title="Primeiro",
        reason="Teste isolado",
    )
    first = ws.start_catalog(person, **args)
    again = ws.start_catalog(person, **args)
    assert (first.replayed, again.replayed) == (False, True)
    assert len(ws.list_drafts()) == 1
    sim = create_simulation(tmp_path / "source")
    content = sim.workspace.view_content(CatalogView(kind="draft", draft_id=sim.draft_id))
    imported = {
        **args,
        "command_id": ws.new_command_id(),
        "namespace": "imported",
        "candidates": canonical_json_bytes(content.model_dump(mode="json")),
        "source_label": "Fonte sintética exportada",
    }
    ws.start_catalog(person, **imported)
    assert ws.start_catalog(person, **imported).replayed
    draft = ws.list_drafts()[-1]
    assert ws.view_content(CatalogView(kind="draft", draft_id=draft.draft_id)) == content
    assert ws.list_releases() == ()


@pytest.mark.parametrize(
    "raw",
    [b"{", b'{"concepts": [], "concepts": []}', b"x" * (8 * 1024 * 1024 + 1)],
    ids=["malformed", "duplicate_key", "oversized"],
)
def test_initial_import_rejects_invalid_or_oversized_input(tmp_path: Path, raw: bytes) -> None:
    ws = CatalogWorkspace(
        open_components(tmp_path / "empty", purpose="synthetic_test"), mode="simulation"
    )
    person = ws.open_session("Pessoa sintética")
    with pytest.raises(WorkspaceError):
        ws.start_catalog(
            person,
            command_id=ws.new_command_id(),
            name="x",
            namespace="x",
            maintainer="x",
            title="x",
            reason="x",
            candidates=raw,
            source_label="x",
        )
    assert ws.list_drafts() == ()


def test_import_cannot_smuggle_approved_entities(tmp_path: Path) -> None:
    sim = create_simulation(tmp_path / "source")
    ws = sim.workspace
    content = ws.view_content(CatalogView(kind="draft", draft_id=sim.draft_id)).model_dump(
        mode="json"
    )
    content["concepts"][0]["lifecycle"] = "approved"
    with pytest.raises(WorkspaceError):
        ws.start_catalog(
            ws.open_session("Pessoa sintética"),
            command_id=ws.new_command_id(),
            name="x",
            namespace="x",
            maintainer="x",
            title="x",
            reason="x",
            candidates=canonical_json_bytes(content),
            source_label="x",
        )
    assert len(ws.list_drafts()) == 1
    assert ws.list_releases() == ()


def test_semantic_authoring_uses_revisions_and_keeps_sources_immutable(tmp_path: Path) -> None:
    sim = create_simulation(tmp_path / "sim")
    ws = sim.workspace
    person = ws.open_session("Pessoa sintética")
    view = CatalogView(kind="draft", draft_id=sim.draft_id)
    original = ws.view_content(view)

    def add(kind: str, fields: dict):
        revision = ws.list_drafts()[0].revision
        args = dict(
            command_id=ws.new_command_id(),
            draft_id=sim.draft_id,
            expected_revision=revision,
            kind=kind,
            fields=fields,
            reason="Teste sintético",
        )
        ws.add_entity(person, **args)
        assert ws.add_entity(person, **args).replayed
        return getattr(ws.view_content(view), kind)[-1]

    unit = add("units", {"symbol": "m", "dimension": "length"})
    domain = add("value_sets", {"value_type": "code", "values": [{"code": "A"}, {"code": "B"}]})
    concept = add(
        "concepts",
        {
            "code": "DISTINCT",
            "labels": [{"lang": "pt-BR", "text": "Distinto"}],
            "definition": [{"lang": "pt-BR", "text": "Método distinto sintético"}],
            "logical_type": "decimal",
            "dimension": "length",
            "unit_id": unit.id,
        },
    )
    assert concept.id not in {c.id for c in original.concepts}
    alias = add(
        "aliases",
        {
            "term": "Busca sintética",
            "purpose": "search",
            "scope": {},
            "target_concept_id": concept.id,
        },
    )
    decision = add(
        "reconciliation_decisions",
        {
            "code": "synthetic-ab",
            "status": "pending",
            "summary": "Divergência sintética",
            "source_assertion_ids": [original.source_assertions[0].id],
        },
    )
    for kind, entity_id, changes in [
        ("concepts", concept.id, {"definition": [{"lang": "pt-BR", "text": "Nova definição"}]}),
        ("units", unit.id, {"reference": "Fonte declarada"}),
        ("value_sets", domain.id, {"ordered": True}),
        ("aliases", alias.id, {"term": "Termo revisado"}),
        (
            "reconciliation_decisions",
            decision.id,
            {"status": "decided", "justification": "Ensaio sintético"},
        ),
    ]:
        ws.edit_entity(
            person,
            command_id=ws.new_command_id(),
            draft_id=sim.draft_id,
            expected_revision=ws.list_drafts()[0].revision,
            kind=kind,
            entity_id=entity_id,
            changes=changes,
            reason="Revisão sintética",
        )
    current = ws.view_content(view)
    assert current.source_assertions == original.source_assertions
    assert current.source_artifacts == original.source_artifacts
    assert current.bindings == original.bindings
    assert all(
        e.lifecycle == "draft" for _, e in current.iter_entities() if hasattr(e, "lifecycle")
    )
    assert ws.list_releases() == ()


def test_authoring_rejects_forged_session_state_and_invalid_decision(tmp_path: Path) -> None:
    sim = create_simulation(tmp_path / "sim")
    ws = sim.workspace
    person = ws.open_session("Pessoa sintética")
    common = dict(
        command_id=ws.new_command_id(),
        draft_id=sim.draft_id,
        expected_revision=1,
        kind="concepts",
        reason="Teste",
    )
    fields = {
        "code": "NEW",
        "labels": [{"lang": "pt-BR", "text": "Novo"}],
        "logical_type": "string",
    }
    forged = WorkspaceSession(
        session_id="forged",
        actor_context_id=person.actor_context_id,
        declared_name=person.declared_name,
        mode="simulation",
    )
    with pytest.raises(WorkspaceError, match="session_unknown"):
        ws.add_entity(forged, fields=fields, **common)
    with pytest.raises(WorkspaceError, match="derived_field"):
        ws.add_entity(person, fields={**fields, "lifecycle": "approved"}, **common)
    with pytest.raises(WorkspaceError):
        ws.add_entity(
            person,
            **{**common, "kind": "reconciliation_decisions"},
            fields={
                "code": "ab",
                "status": "decided",
                "summary": "x",
                "source_assertion_ids": ["synthetic:one"],
            },
        )
    assert ws.list_drafts()[0].revision == 1


def test_schema_generator_writes_only_the_configured_synthetic_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(schema, "BASE_DIR", tmp_path)
    assert schema.main() == 0
    assert (tmp_path / schema.SCHEMA_PATH).read_bytes() == canonical_json_bytes(
        schema.catalog_json_schema()
    )


def test_exported_bsdd_candidates_enter_workspace_as_draft(tmp_path: Path) -> None:
    from tests.domain_catalog.test_bsdd_curation import _staged

    staged = _staged(tmp_path)
    ws = CatalogWorkspace(
        open_components(tmp_path / "target", purpose="synthetic_test"), mode="simulation"
    )
    person = ws.open_session("Pessoa sintética")
    args = dict(
        command_id=ws.new_command_id(),
        name="bSDD sintético",
        namespace="synthetic",
        maintainer="Teste",
        title="Importação",
        reason="Ensaio sintético",
        candidates=(tmp_path / "staging" / "candidates.json").read_bytes(),
        source_label="Staging bSDD sintético reaberto",
    )
    ws.start_catalog(person, **args)
    assert ws.start_catalog(person, **args).replayed
    draft = ws.list_drafts()[0]
    assert ws.view_content(CatalogView(kind="draft", draft_id=draft.draft_id)) == staged.content
    assert ws.list_releases() == ()
