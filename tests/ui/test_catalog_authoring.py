"""Percursos reais da página de autoria com dados sintéticos isolados."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.domain_catalog.workspace import CatalogWorkspace, open_components
from src.domain_catalog.workspace_models import CatalogView
from tests.ui.test_catalog_page import _approve_and_prepare, _button, _start, _ws

pytest_plugins = ["tests.ui.test_catalog_page"]


def _input(at: AppTest, label: str, text: str, area: bool = False) -> None:
    widgets = at.text_area if area else at.text_input
    next(w for w in widgets if w.label == label).input(text)


def test_empty_initialized_area_to_distinct_concept_without_json(
    app: AppTest, tmp_path: Path
) -> None:
    ws = CatalogWorkspace(
        open_components(tmp_path / "empty", purpose="synthetic_test"), mode="simulation"
    )
    app.session_state["catalog_ws"] = ws
    app.session_state["catalog_session"] = ws.open_session("Pessoa sintética")
    app.run()
    for suffix, text in [
        ("name", "Catálogo sintético"),
        ("namespace", "synthetic"),
        ("maintainer", "Teste"),
        ("title", "Primeiro"),
        ("reason", "Ensaio"),
    ]:
        app.text_input(key=f"catalog_first_{suffix}").input(text)
    _button(app, "Criar primeiro rascunho").click().run()
    assert not app.exception
    assert len(ws.list_drafts()) == 1
    _input(app, "Código do conceito", "DISTINCT")
    _input(app, "Rótulo (pt-BR)", "Distinto")
    _input(app, "Definição (pt-BR)", "Método sintético distinto", area=True)
    _input(app, "Motivo da alteração semântica", "Autoria sintética")
    _button(app, "Salvar proposta semântica").click().run()
    assert not app.exception
    draft = ws.list_drafts()[0]
    content = ws.view_content(CatalogView(kind="draft", draft_id=draft.draft_id))
    assert content.concepts[0].code == "DISTINCT"
    assert content.concepts[0].lifecycle == "draft"
    assert ws.list_releases() == ()


def test_semantic_forms_save_units_domains_aliases_and_ab_decision(app: AppTest) -> None:
    _start(app)
    ws = _ws(app)
    draft = ws.list_drafts()[0]
    view = CatalogView(kind="draft", draft_id=draft.draft_id)
    original = ws.view_content(view)
    app.selectbox(key="catalog_sem_kind").select("Unidade").run()
    _input(app, "Símbolo", "m")
    _input(app, "Motivo da alteração semântica", "Unidade sintética")
    _button(app, "Salvar proposta semântica").click().run()
    assert not app.exception
    assert any(u.symbol == "m" for u in ws.view_content(view).units)
    app.selectbox(key="catalog_sem_kind").select("Domínio de valores").run()
    _input(app, "Valores permitidos (um por linha; booleanos: true/false)", "X\nY", area=True)
    _input(app, "Motivo da alteração semântica", "Domínio sintético")
    _button(app, "Salvar proposta semântica").click().run()
    assert not app.exception
    assert any([v.code for v in s.values] == ["X", "Y"] for s in ws.view_content(view).value_sets)
    app.selectbox(key="catalog_sem_kind").select("Alias").run()
    _input(app, "Termo do alias", "Busca sintética")
    next(w for w in app.selectbox if w.label == "Alvo do alias").select(original.concepts[0].id)
    _input(app, "Motivo da alteração semântica", "Alias sintético")
    _button(app, "Salvar proposta semântica").click().run()
    assert not app.exception
    assert any(a.term == "Busca sintética" for a in ws.view_content(view).aliases)
    app.selectbox(key="catalog_sem_kind").select("Decisão A/B").run()
    _input(app, "Código da decisão", "synthetic-ab")
    _input(app, "Divergência A/B", "Divergência sintética", area=True)
    next(w for w in app.multiselect if w.label == "Assertivas de origem").select(
        original.source_assertions[0].id
    )
    _input(app, "Motivo da alteração semântica", "Decisão sintética pendente")
    _button(app, "Salvar proposta semântica").click().run()
    assert not app.exception
    assert any(
        d.code == "synthetic-ab" and d.status == "pending"
        for d in ws.view_content(view).reconciliation_decisions
    )
    assert ws.view_content(view).source_assertions == original.source_assertions
    assert ws.list_releases() == ()


def test_semantic_conflict_reload_and_successive_edits_keep_intent(app: AppTest) -> None:
    _start(app)
    ws = _ws(app)
    draft = ws.list_drafts()[0]
    view = CatalogView(kind="draft", draft_id=draft.draft_id)
    concept = ws.view_content(view).concepts[0]
    original = next(t.text for t in concept.definition if t.lang == "pt-BR")
    app.selectbox(key="catalog_sem_pick_concepts").select(concept.id).run()
    _input(app, "Definição (pt-BR)", "Edição local não salva", area=True)
    _input(app, "Motivo da alteração semântica", "Teste concorrente")
    other = ws.open_session("Outra pessoa sintética")
    ws.edit_entity(
        other,
        command_id=ws.new_command_id(),
        draft_id=draft.draft_id,
        expected_revision=draft.revision,
        kind="concepts",
        entity_id=concept.id,
        changes={"labels": [{"lang": "pt-BR", "text": "Rótulo concorrente"}]},
        reason="Mudança concorrente sintética",
    )
    _button(app, "Salvar proposta semântica").click().run()
    assert any("revision_conflict" in t.value for t in app.error)
    _button(app, "Recarregar revisão atual").click().run()
    assert app.selectbox(key="catalog_sem_pick_concepts").value == concept.id
    assert (
        next(w for w in app.text_area if w.label == "Definição (pt-BR)").value
        == "Edição local não salva"
    )
    _button(app, "Salvar proposta semântica").click().run()
    assert not app.exception
    current = next(c for c in ws.view_content(view).concepts if c.id == concept.id)
    assert current.labels[0].text == "Rótulo concorrente"
    assert current.definition[0].text == "Edição local não salva"
    app.selectbox(key="catalog_sem_pick_concepts").select(concept.id).run()
    _input(app, "Definição (pt-BR)", original, area=True)
    _input(app, "Motivo da alteração semântica", "Voltar ao texto original explicitamente")
    _button(app, "Salvar proposta semântica").click().run()
    current = next(c for c in ws.view_content(view).concepts if c.id == concept.id)
    assert current.definition[0].text == original
    assert current.labels[0].text == "Rótulo concorrente"


@pytest.mark.parametrize("state", ["in_review", "approved"])
def test_semantic_edit_after_review_invalidates_approval(app: AppTest, state: str) -> None:
    _start(app)
    ws = _ws(app)
    draft = ws.list_drafts()[0]
    view = CatalogView(kind="draft", draft_id=draft.draft_id)
    concept = ws.view_content(view).concepts[0]
    if state == "approved":
        _approve_and_prepare(app, ws)
    else:
        app.text_input(key="catalog_sub_reason").input("revisão sintética")
        app.checkbox(key="catalog_sub_confirm").check()
        _button(app, "Enviar para revisão humana").click().run()
    assert not app.exception
    assert ws.list_drafts()[0].state == state
    app.selectbox(key="catalog_sem_pick_concepts").select(concept.id).run()
    _input(app, "Definição (pt-BR)", "Revisão sintética posterior", area=True)
    _input(app, "Motivo da alteração semântica", "Correção após revisão")
    _button(app, "Salvar proposta semântica").click().run()
    assert not app.exception
    changed = ws.list_drafts()[0]
    assert changed.state == "editing"
    assert changed.candidate_id is None
    assert next(c for c in ws.view_content(view).concepts if c.id == concept.id).definition[
        0
    ].text == ("Revisão sintética posterior")
    assert ws.list_releases() == ()
