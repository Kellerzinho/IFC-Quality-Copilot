"""Área de trabalho do catálogo (M1-14, E5): abertura, identificação e abas.

Componente do shell Streamlit existente. Consome somente a fachada
``src.domain_catalog.workspace``; não escreve JSON publicado nem banco, não informa
papel/``actor_kind`` ao backend e não habilita capacidade não implementada. Texto vindo
de catálogo, IFC, IDS ou fonte é exibido como texto puro (``st.text``/tabelas), nunca
como Markdown/HTML. A UI de uso aprovada para a M4 é React/TypeScript com API Python;
esta fatia é a ligação mínima ao shell disponível neste checkout.
"""

import os
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

import streamlit as st

from src.domain_catalog.workspace import CatalogWorkspace, open_operational_workspace
from src.domain_catalog.workspace_models import (
    IDENTITY_NOTICE,
    SIMULATION_NOTICE,
    ActionReceipt,
    FieldIssue,
    WorkspaceError,
    WorkspaceSession,
)

WS_KEY = "catalog_ws"
SESSION_KEY = "catalog_session"
LAST_KEY = "catalog_last_receipt"
ROOT_ENV = "IFCQC_CATALOG_ROOT"
"""Raiz operacional configurada no servidor; a interface nunca recebe caminho do navegador."""


def workspace() -> CatalogWorkspace:
    """Área de trabalho aberta nesta sessão do servidor."""
    found = st.session_state.get(WS_KEY)
    assert isinstance(found, CatalogWorkspace)
    return found


def current_session() -> WorkspaceSession | None:
    """Sessão de ator emitida pelo backend, se a pessoa já se identificou."""
    found = st.session_state.get(SESSION_KEY)
    return found if isinstance(found, WorkspaceSession) else None


def command_key(action: str) -> str:
    """Chave idempotente da ação, mantida até a resposta definitiva."""
    key = f"catalog_cmd_{action}"
    if key not in st.session_state:
        st.session_state[key] = CatalogWorkspace.new_command_id()
    return str(st.session_state[key])


def show_issues(issues: tuple[FieldIssue, ...]) -> None:
    """Problemas por entidade/campo, como tabela de dados (texto puro)."""
    if issues:
        st.dataframe(
            [
                {
                    "Severidade": i.severity,
                    "Código": i.code,
                    "Entidade": i.entity_kind or "—",
                    "ID": i.entity_id or "—",
                    "Campo": i.field or "—",
                    "Mensagem": i.message,
                }
                for i in issues
            ],
            hide_index=True,
            width="stretch",
        )


def show_error(error: WorkspaceError) -> None:
    """Mensagem útil, sem caminhos, com orientação sobre o que foi preservado."""
    st.error(f"Ação recusada ou falhou — código {error.code}")
    st.text(error.message)
    show_issues(error.issues)
    if error.retry_same_key:
        st.info("Repetir esta ação reutiliza a mesma chave: não haverá duplicidade.")
    elif error.keep_input:
        st.info("Os dados digitados foram mantidos nos campos para correção.")


def run_action(action: str, call: Callable[[str], ActionReceipt]) -> ActionReceipt | None:
    """Executa um comando com chave idempotente; descarta a chave só quando é seguro.

    Sucesso grava o recibo e reexecuta a página para mostrar o estado novo.
    """
    key = command_key(action)
    try:
        receipt = call(key)
    except WorkspaceError as error:
        if not error.retry_same_key:
            st.session_state.pop(f"catalog_cmd_{action}", None)
        show_error(error)
        return None
    st.session_state.pop(f"catalog_cmd_{action}", None)
    st.session_state[LAST_KEY] = receipt
    kind, _, subject = receipt.subject.partition(" ")
    if kind == "draft" and receipt.revision is not None:
        st.session_state[f"catalog_seen_{subject}"] = receipt.revision
    st.rerun()


def safe_text(label: str, value: object) -> None:
    """Rótulo nosso + valor de dado, sempre como texto puro."""
    st.text(f"{label}: {'—' if value in (None, '', ()) else value}")


def _open_operational() -> None:
    root = os.environ.get(ROOT_ENV)
    if not root:
        st.info(
            "Área operacional não configurada neste servidor (variável de ambiente "
            f"{ROOT_ENV}). Use a simulação sintética para ensaiar o fluxo."
        )
        return
    if st.button("Abrir área operacional configurada", key="catalog_open_operational"):
        from src.suggestion_engine.catalog_operations import build_e3_operation_bundle

        try:
            st.session_state[WS_KEY] = open_operational_workspace(
                Path(root), registry=build_e3_operation_bundle().registry
            )
        except WorkspaceError as error:
            show_error(error)
            return
        except Exception as error:  # banco ilegível: sem caminho na mensagem
            st.error(
                "Não foi possível abrir a área operacional configurada "
                f"({type(error).__name__}). Inicialize-a pelo procedimento operacional."
            )
            return
        st.rerun()


def _open_simulation() -> None:
    st.write(SIMULATION_NOTICE)
    if st.button("Iniciar simulação sintética", key="catalog_open_simulation"):
        from src.domain_catalog.workspace_simulation import create_simulation

        holder = Path(tempfile.mkdtemp(prefix="ifcqc-e5-sim-"))
        try:
            with st.spinner("Montando simulação isolada..."):
                simulation = create_simulation(holder / "sim")
        except Exception as error:  # falha da semente: limpa a pasta temporária nova
            shutil.rmtree(holder, ignore_errors=True)
            st.error(f"A simulação não pôde ser montada ({type(error).__name__}); nada foi aberto.")
            return
        st.session_state[WS_KEY] = simulation.workspace
        st.rerun()


def _render_identity(ws: CatalogWorkspace) -> WorkspaceSession | None:
    session = current_session()
    st.caption(IDENTITY_NOTICE)
    if session is None or session.mode != ws.mode:
        with st.form("catalog_identity_form"):
            name = st.text_input(
                "Nome declarado (identifica; não autentica)", key="catalog_declared_name"
            )
            if st.form_submit_button("Identificar-me"):
                try:
                    st.session_state[SESSION_KEY] = ws.open_session(name)
                    st.rerun()
                except WorkspaceError as error:
                    show_error(error)
        return None
    safe_text("Identificação informada (unverified_local)", session.declared_name or "sem nome")
    if st.button("Trocar identificação", key="catalog_switch_identity"):
        st.session_state.pop(SESSION_KEY, None)
        st.rerun()
    return session


def render_catalog_workspace() -> None:
    """Tela de curadoria do catálogo: tabela, curadoria, publicação, projeto e análise."""
    from src.ui.components.catalog_curation import render_curation_tab, render_publication_tab
    from src.ui.components.catalog_project import render_analysis_tab, render_project_tab
    from src.ui.components.catalog_table import render_table_tab, selected_view

    st.title("Catálogo de domínio — curadoria (M1)")
    if WS_KEY not in st.session_state:
        st.subheader("Abrir área de trabalho")
        _open_operational()
        _open_simulation()
        return
    ws = workspace()
    if ws.mode == "simulation":
        st.warning(SIMULATION_NOTICE)
    else:
        st.info(
            "Área operacional: publicar e adotar são decisões humanas reais e distintas; "
            "nenhuma delas altera o IFC."
        )
    session = _render_identity(ws)
    last = st.session_state.get(LAST_KEY)
    if isinstance(last, ActionReceipt):
        st.success("Última ação confirmada pelo serviço.")
        st.text(last.message)
        safe_text("Recibo", f"{last.operation} · {last.subject} · chave {last.command_id}")
    try:
        view = selected_view(ws)
    except WorkspaceError as error:
        show_error(error)
        view = None
    tabs = st.tabs(["Tabela", "Curadoria", "Publicação", "Projeto e pin", "Análise"])
    with tabs[0]:
        render_table_tab(ws, view)
    with tabs[1]:
        render_curation_tab(ws, session, view)
    with tabs[2]:
        render_publication_tab(ws, session)
    with tabs[3]:
        render_project_tab(ws, session)
    with tabs[4]:
        render_analysis_tab(ws, session)
