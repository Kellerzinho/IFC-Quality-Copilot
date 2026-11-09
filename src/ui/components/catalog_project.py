"""Pacote fixado no projeto, diff/impacto, adoção/rollback e análise (M1-14, E5).

Adotar um release é decisão distinta de publicá-lo: o plano mostra diff e impacto e só
é aplicado com confirmação do ID e do hash exatos; cria novo pin e nova análise sem
transportar aprovações. A análise mostra estado IDS, estado de mapeamento e estado de
evidência em colunas separadas, por elemento ou por requisito; nada altera o IFC.
"""

import streamlit as st

from src.domain_catalog.workspace import CatalogWorkspace
from src.domain_catalog.workspace_models import (
    ActionReceipt,
    AdoptionPreview,
    WorkspaceError,
    WorkspaceSession,
)
from src.ui.components.catalog_workspace import run_action, safe_text, show_error

PREVIEW_KEY = "catalog_adoption_preview"


def _project(ws: CatalogWorkspace, key: str) -> str | None:
    projects = dict((f"{name} · {pid}", pid) for pid, name in ws.list_projects())
    if not projects:
        st.info("Nenhum projeto na área de trabalho.")
        return None
    return projects[st.selectbox("Projeto", list(projects), key=key)]


def render_project_tab(ws: CatalogWorkspace, session: WorkspaceSession | None) -> None:
    """Pin vigente, histórico de pins e plano explícito de adoção/rollback."""
    try:
        project_id = _project(ws, "catalog_project_pick")
        if project_id is None:
            return
        pin = ws.pin_view(project_id)
        safe_text("Projeto", pin.project_name)
        safe_text(
            "Catálogo fixado",
            "nenhum (projeto ainda sem pin)"
            if pin.catalog is None
            else f"{pin.catalog.version} · {pin.catalog.manifest_sha256}",
        )
        safe_text("Revisão do pin", pin.pin_revision)
        safe_text("Pares ativos", ", ".join(pin.pairs))
        for line in pin.history:
            st.text(line)
        if session is None:
            st.info("Identifique-se no topo da página para preparar adoção.")
            return
        releases = {f"{r.version} · {r.manifest_sha256[:12]}…": r for r in ws.list_releases()}
        if not releases:
            st.info("Nenhum release publicado para adotar.")
            return
        with st.form("catalog_adoption_form"):
            target = st.selectbox("Release alvo", list(releases), key="catalog_adopt_target")
            intent = st.selectbox(
                "Intenção", ("initial", "update", "rollback"), key="catalog_adopt_intent"
            )
            reason = st.text_input("Motivo", key="catalog_adopt_reason")
            if st.form_submit_button("Preparar plano (não muda o pin)"):
                st.session_state[PREVIEW_KEY] = ws.preview_adoption(
                    session,
                    project_id=project_id,
                    target=releases[target],
                    intent=intent,  # type: ignore[arg-type]
                    reason=reason,
                )
        preview = st.session_state.get(PREVIEW_KEY)
        if isinstance(preview, AdoptionPreview):
            _render_preview(ws, session, project_id, preview)
    except WorkspaceError as error:
        show_error(error)


def _render_preview(
    ws: CatalogWorkspace, session: WorkspaceSession, project_id: str, preview: AdoptionPreview
) -> None:
    st.subheader("Plano de adoção — diff e impacto")
    safe_text("Plano", f"{preview.plan_id} · hash {preview.plan_sha256}")
    safe_text("Intenção", preview.intent)
    safe_text("De", None if preview.old_catalog is None else preview.old_catalog.version)
    safe_text("Para", preview.target_catalog.version)
    if preview.diff_absent_reason:
        safe_text("Diff", f"indisponível ({preview.diff_absent_reason})")
    for line in preview.diff_lines:
        st.text(f"diff: {line}")
    for line in preview.impact_lines:
        st.text(f"impacto: {line}")
    safe_text("Reprocessamento", f"{preview.reanalysis_scope} ({preview.pairs} par(es))")
    st.text(preview.statement)
    with st.form("catalog_apply_form"):
        confirm = st.checkbox(
            f"Confirmo o plano {preview.plan_id[:8]}… com hash {preview.plan_sha256[:12]}…",
            key="catalog_apply_confirm",
        )
        if st.form_submit_button("Aplicar plano exato") and confirm:

            def apply(key: str) -> ActionReceipt:
                receipt = ws.apply_adoption(
                    session,
                    command_id=key,
                    project_id=project_id,
                    plan_id=preview.plan_id,
                    plan_sha256=preview.plan_sha256,
                )
                st.session_state.pop(PREVIEW_KEY, None)
                return receipt

            run_action(f"adopt_{preview.plan_id}", apply)


def render_analysis_tab(ws: CatalogWorkspace, session: WorkspaceSession | None) -> None:
    """Análises do projeto com estados IDS/mapeamento/evidência separados."""
    try:
        project_id = _project(ws, "catalog_analysis_project")
        if project_id is None:
            return
        analyses = ws.list_analyses(project_id)
        if (
            session is not None
            and any(state == "queued" for _, state, _ in analyses)
            and st.button(
                "Executar análises enfileiradas (somente leitura do IFC)",
                key="catalog_run_analyses",
            )
        ):
            with st.spinner("Executando análise local..."):
                for line in ws.execute_queued_analyses(session, project_id):
                    st.text(line)
            analyses = ws.list_analyses(project_id)
        if not analyses:
            st.info("Nenhuma análise; adote um release para enfileirar.")
            return
        labels = {f"{aid} · {state} · pin r{pin}": aid for aid, state, pin in analyses}
        chosen = st.selectbox("Análise", list(labels), key="catalog_analysis_pick")
        group = st.radio(
            "Navegar por",
            ("element", "requirement"),
            key="catalog_analysis_group",
            format_func=lambda g: "elemento" if g == "element" else "requisito",
        )
        view = ws.analysis_view(labels[chosen], group)  # type: ignore[arg-type]
    except WorkspaceError as error:
        show_error(error)
        return
    safe_text("Estado", view.state)
    safe_text("Catálogo da análise", None if view.catalog is None else view.catalog.version)
    st.dataframe(
        [
            {
                "Elemento": r.element,
                "Requisito": r.requirement,
                "Esperado (IDS)": r.expected,
                "Encontrado": r.found,
                "Origem": r.origin,
                "Estado IDS": r.ids_state,
                "Mapeamento": r.mapping_state,
                "Evidência": r.evidence_state,
                "Detalhe da evidência": r.evidence_detail or "—",
            }
            for r in view.rows
        ],
        hide_index=True,
        width="stretch",
    )
    st.caption(
        "Estado IDS, mapeamento e evidência são independentes. Proposta de evidência não "
        "é valor aprovado; nenhuma alteração do IFC é feita aqui."
    )
    for limitation in view.limitations:
        st.text(f"Limitação: {limitation}")
