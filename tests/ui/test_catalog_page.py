"""Página de curadoria do catálogo (M1-14/M1-17) no shell Streamlit, via AppTest.

Percorre a página real em SIMULAÇÃO sintética (pasta temporária, banco
``synthetic_test``), com rede bloqueada: identificar-se, filtrar, cadastrar uso com
operação existente sem editar JSON, revisar a revisão/hash exatos, preparar e publicar
(simulado), adotar com plano exato e ver a análise com estados separados. Testes
automatizados não substituem observação humana de usabilidade (teclado/foco).
"""

import re
import socket
import tempfile
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("streamlit.testing.v1")

from streamlit.testing.v1 import AppTest

from src.domain_catalog.workspace import CatalogWorkspace
from src.domain_catalog.workspace_models import CatalogView
from src.domain_catalog.workspace_simulation import SIM_B_METODO, SIM_P_RECOVER

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "src" / "ui" / "pages" / "catalogo.py"
UI_FILES = [PAGE, *sorted((ROOT / "src" / "ui" / "components").glob("catalog_*.py"))]


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppTest:
    def _no_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("a página tentou acessar a rede")

    monkeypatch.setattr(socket.socket, "connect", _no_network)
    monkeypatch.setattr(socket, "create_connection", _no_network)
    monkeypatch.setattr(socket, "getaddrinfo", _no_network)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.delenv("IFCQC_CATALOG_ROOT", raising=False)
    at = AppTest.from_file(str(PAGE), default_timeout=180)
    at.run()
    return at


def _button(at: AppTest, label: str) -> Any:
    return next(b for b in at.button if b.label == label)


def _ws(at: AppTest) -> CatalogWorkspace:
    found = at.session_state["catalog_ws"]
    assert isinstance(found, CatalogWorkspace)
    return found


def _texts(at: AppTest) -> list[str]:
    return [t.value for t in at.text]


def _start(at: AppTest) -> None:
    _button(at, "Iniciar simulação sintética").click().run()
    at.text_input(key="catalog_declared_name").input("Pessoa Sintética (teste de UI)")
    _button(at, "Identificar-me").click().run()
    assert not at.exception


def test_opening_offers_simulation_and_explains_missing_operational_root(app: AppTest) -> None:
    assert not app.exception
    assert app.title[0].value.startswith("Catálogo de domínio")
    assert any("não configurada" in i.value for i in app.info)
    _button(app, "Iniciar simulação sintética").click().run()
    assert any("SIMULAÇÃO" in w.value for w in app.warning)
    assert "catalog_session" not in app.session_state
    assert any("Identifique-se" in i.value for i in app.info)


def test_operational_root_without_database_is_not_created_from_the_ui(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "operacional"
    monkeypatch.setenv("IFCQC_CATALOG_ROOT", str(root))
    at = AppTest.from_file(str(PAGE), default_timeout=120)
    at.run()
    _button(at, "Abrir área operacional configurada").click().run()
    assert not at.exception
    assert any("nada foi criado" in t for t in _texts(at))
    assert not (root / "db" / "operations.sqlite3").exists()
    assert str(root) not in " ".join(e.value for e in at.error)


def test_full_simulated_path_through_the_page(app: AppTest) -> None:
    _start(app)
    ws = _ws(app)
    assert len(app.dataframe[0].value) == 2

    app.selectbox(key="catalog_filter_class").select("IfcSlab").run()
    assert len(app.dataframe[0].value) == 2

    app.text_input(key="catalog_au_classes").input("IfcColumn")
    app.text_input(key="catalog_au_set").input("SIM_Conjunto")
    app.text_input(key="catalog_au_field").input("SIM_Metodo")
    app.text_input(key="catalog_au_type").input("IfcLabel")
    policy = next(o for o in app.selectbox(key="catalog_au_policy").options if SIM_P_RECOVER in o)
    app.selectbox(key="catalog_au_policy").select(policy)
    app.text_input(key="catalog_au_reason").input("mesmo conceito em pilares")
    _button(app, "Salvar uso no rascunho").click().run()
    assert not app.exception
    (draft,) = ws.list_drafts()
    assert draft.revision == 2
    assert len(ws.rows(CatalogView(kind="draft", draft_id=draft.draft_id))) == 3
    assert "catalog_cmd_add_usage" not in app.session_state

    app.text_input(key="catalog_sub_reason").input("pronto")
    app.checkbox(key="catalog_sub_confirm").check()
    _button(app, "Enviar para revisão humana").click().run()
    assert ws.list_drafts()[0].state == "in_review"

    app.radio(key="catalog_rev_verdict").set_value("approve")
    app.text_area(key="catalog_rev_justification").input("Conferência sintética de UI.")
    _button(app, "Registrar revisão").click().run()
    assert ws.list_drafts()[0].state == "in_review"
    app.checkbox(key="catalog_rev_confirm").check()
    _button(app, "Registrar revisão").click().run()
    assert ws.list_drafts()[0].state == "approved"
    assert ws.list_releases() == ()

    draft_id = ws.list_drafts()[0].draft_id
    app.text_input(key=f"catalog_prep_v_{draft_id}").input("1.0.0")
    app.text_input(key=f"catalog_prep_t_{draft_id}").input("sintético, sem terceiros")
    app.text_input(key=f"catalog_prep_r_{draft_id}").input("preparar")
    _button(app, "Preparar candidato (não publica)").click().run()
    candidate_id = ws.list_drafts()[0].candidate_id
    assert candidate_id is not None
    assert ws.list_releases() == ()

    app.text_input(key=f"catalog_pub_v_{candidate_id}").input("9.9.9")
    app.text_area(key=f"catalog_pub_j_{candidate_id}").input("Publicação simulada de UI.")
    _button(app, "Publicar este candidato").click().run()
    assert any("não confere" in e.value for e in app.error)
    assert ws.list_releases() == ()
    app.text_input(key=f"catalog_pub_v_{candidate_id}").input("1.0.0")
    _button(app, "Publicar este candidato").click().run()
    (release,) = ws.list_releases()
    assert release.version == "1.0.0"

    app.selectbox(key="catalog_adopt_intent").select("initial")
    app.text_input(key="catalog_adopt_reason").input("adotar r1")
    _button(app, "Preparar plano (não muda o pin)").click().run()
    project_id = ws.list_projects()[0][0]
    assert ws.pin_view(project_id).pin_revision == 0
    _button(app, "Aplicar plano exato").click().run()
    assert ws.pin_view(project_id).pin_revision == 0
    app.checkbox(key="catalog_apply_confirm").check()
    _button(app, "Aplicar plano exato").click().run()
    assert ws.pin_view(project_id).pin_revision == 1
    assert not app.exception


def test_analysis_tab_shows_three_separate_states(app: AppTest) -> None:
    pytest.importorskip("ifctester", reason="extra e3 não instalado (ifctester==0.8.5)")
    test_full_simulated_path_through_the_page(app)
    _button(app, "Executar análises enfileiradas (somente leitura do IFC)").click().run()
    assert not app.exception
    frames = [f.value for f in app.dataframe]
    analysis = next(f for f in frames if "Estado IDS" in f.columns)
    assert set(analysis["Estado IDS"]) == {"non_compliant"}
    assert set(analysis["Mapeamento"]) == {"resolved"}
    assert set(analysis["Evidência"]) == {"proposed", "abstained"}


def test_conflicting_edit_keeps_typed_values_and_shows_a_useful_message(app: AppTest) -> None:
    _start(app)
    ws = _ws(app)
    (draft,) = ws.list_drafts()
    app.text_input(key="catalog_au_classes").input("IfcBeam")
    app.text_input(key="catalog_au_set").input("SIM_Conjunto")
    app.text_input(key="catalog_au_field").input("SIM_Metodo")
    app.text_input(key="catalog_au_reason").input("vigas")
    other = ws.open_session("Outra Pessoa Sintética")
    ws.edit_entity(
        other,
        command_id=ws.new_command_id(),
        draft_id=draft.draft_id,
        expected_revision=draft.revision,
        kind="bindings",
        entity_id=SIM_B_METODO,
        changes={"notes": "edição concorrente"},
        reason="concorrência",
    )
    _button(app, "Salvar uso no rascunho").click().run()
    assert any("revision_conflict" in e.value for e in app.error)
    assert any("preservada" in t for t in _texts(app))
    assert app.text_input(key="catalog_au_classes").value == "IfcBeam"
    assert app.text_input(key="catalog_au_field").value == "SIM_Metodo"
    assert ws.list_drafts()[0].revision == draft.revision + 1


def test_untrusted_catalog_text_is_rendered_as_plain_text(app: AppTest) -> None:
    _start(app)
    ws = _ws(app)
    (draft,) = ws.list_drafts()
    hostile = "**negrito** <script>alert(1)</script> [link](http://exemplo.invalido)"
    ws.edit_entity(
        ws.open_session("Pessoa Sintética"),
        command_id=ws.new_command_id(),
        draft_id=draft.draft_id,
        expected_revision=draft.revision,
        kind="bindings",
        entity_id=SIM_B_METODO,
        changes={"notes": hostile},
        reason="texto hostil sintético",
    )
    app.run()
    assert any("O rascunho mudou" in w.value for w in app.warning)
    assert not any(hostile in t for t in _texts(app))
    _button(app, "Recarregar revisão atual").click().run()
    assert any(hostile in t for t in _texts(app))
    rendered = " ".join(m.value for m in app.markdown)
    assert "<script>" not in rendered
    assert "exemplo.invalido" not in rendered


@pytest.mark.parametrize("path", UI_FILES, ids=lambda p: p.name)
def test_ui_slice_has_no_remote_assets_or_raw_html(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    assert not re.search(r"https?://", source)
    assert "unsafe_allow_html" not in source
    assert "components.html" not in source
    assert "st.image(" not in source


def test_main_shell_navigates_to_the_catalog_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _no_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("o shell tentou acessar a rede")

    monkeypatch.setattr(socket.socket, "connect", _no_network)
    monkeypatch.setattr(socket, "getaddrinfo", _no_network)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    at = AppTest.from_file(str(ROOT / "src" / "ui" / "app.py"), default_timeout=180)
    at.switch_page("pages/catalogo.py")
    at.run()
    assert not at.exception
    assert at.title[0].value.startswith("Catálogo de domínio")


def _approve_and_prepare(app: AppTest, ws: CatalogWorkspace) -> str:
    app.text_input(key="catalog_sub_reason").input("pronto")
    app.checkbox(key="catalog_sub_confirm").check()
    _button(app, "Enviar para revisão humana").click().run()
    app.text_area(key="catalog_rev_justification").input("Conferência sintética de UI.")
    app.checkbox(key="catalog_rev_confirm").check()
    _button(app, "Registrar revisão").click().run()
    draft_id = ws.list_drafts()[0].draft_id
    app.text_input(key=f"catalog_prep_v_{draft_id}").input("1.0.0")
    app.text_input(key=f"catalog_prep_t_{draft_id}").input("sintético, sem terceiros")
    app.text_input(key=f"catalog_prep_r_{draft_id}").input("preparar")
    _button(app, "Preparar candidato (não publica)").click().run()
    candidate_id = ws.list_drafts()[0].candidate_id
    assert candidate_id is not None
    return candidate_id


def test_selected_draft_stays_selected_when_its_state_changes(app: AppTest) -> None:
    _start(app)
    ws = _ws(app)
    (draft,) = ws.list_drafts()
    person = ws.open_session("Outra Pessoa Sintética")
    ws.create_draft(
        person,
        command_id=ws.new_command_id(),
        title=draft.title,
        reason="mesmo título",
        catalog=ws.components.curation.get_draft(draft.draft_id).catalog,
    )
    app.run()
    keys = app.selectbox(key="catalog_view").options
    assert len(set(keys)) == len(keys) == 2
    app.selectbox(key="catalog_view").set_value(f"draft:{draft.draft_id}").run()
    app.text_input(key="catalog_sub_reason").input("pronto")
    app.checkbox(key="catalog_sub_confirm").check()
    _button(app, "Enviar para revisão humana").click().run()
    assert ws.components.curation.get_draft(draft.draft_id).state == "in_review"
    assert app.selectbox(key="catalog_view").value == f"draft:{draft.draft_id}"


def test_interrupted_publication_can_be_resumed_from_the_page(
    app: AppTest, monkeypatch: pytest.MonkeyPatch
) -> None:
    _start(app)
    ws = _ws(app)
    candidate_id = _approve_and_prepare(app, ws)
    releases = ws.components.releases
    real_promote = releases.promote

    def interrupted(*args: object, **kwargs: object) -> Path:
        raise OSError(5, "falha simulada de disco")

    monkeypatch.setattr(releases, "promote", interrupted)
    app.text_input(key=f"catalog_pub_v_{candidate_id}").input("1.0.0")
    app.text_area(key=f"catalog_pub_j_{candidate_id}").input("Publicação simulada.")
    _button(app, "Publicar este candidato").click().run()
    assert any("publication_incomplete" in e.value for e in app.error)
    assert ws.list_releases() == ()
    monkeypatch.setattr(releases, "promote", real_promote)
    app.run()
    app.radio(key="catalog_intent_action").set_value("retomar")
    app.text_input(key="catalog_intent_reason").input("retomar publicação interrompida")
    _button(app, "Registrar").click().run()
    assert not app.exception
    assert [r.version for r in ws.list_releases()] == ["1.0.0"]
    assert ws.pending_intents() == ()
