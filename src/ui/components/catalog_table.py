"""Tabela do catálogo com filtros e detalhe do uso (M1-14, E5).

Fonte, classe, perfil e estado filtram linhas de uso (binding). O detalhe separa
conceito e binding, original e reconciliado, aplicabilidade, aliases, capacidade,
proveniência e histórico. Somente leitura: as ações ficam na aba de curadoria.
"""

import streamlit as st

from src.domain_catalog.workspace import CatalogWorkspace
from src.domain_catalog.workspace_models import CatalogView, RowFilters, WorkspaceError
from src.ui.components.catalog_workspace import safe_text, show_error

VIEW_KEY = "catalog_view"
SEEN_PREFIX = "catalog_seen_"
ROW_KEY = "catalog_selected_binding"
ALL = "(todos)"


def view_options(ws: CatalogWorkspace) -> dict[str, tuple[str, CatalogView]]:
    """Opções por chave estável (ID do rascunho ou hash do release) → (rótulo, conteúdo).

    A chave não depende de título, estado ou revisão: a seleção da pessoa não troca
    sozinha quando o rascunho muda, e títulos repetidos continuam distinguíveis.
    """
    options: dict[str, tuple[str, CatalogView]] = {}
    for draft in ws.list_drafts():
        options[f"draft:{draft.draft_id}"] = (
            f"Rascunho «{draft.title}» · {draft.state} · {draft.draft_id[-12:]}",
            CatalogView(kind="draft", draft_id=draft.draft_id),
        )
    for release in ws.list_releases():
        options[f"release:{release.catalog_id}:{release.version}:{release.manifest_sha256}"] = (
            f"Release publicado {release.version} · {release.manifest_sha256[:12]}…",
            CatalogView(kind="release", release=release),
        )
    return options


def selected_view(ws: CatalogWorkspace) -> CatalogView | None:
    """Conteúdo escolhido pela pessoa (o mesmo para todas as abas)."""
    options = view_options(ws)
    if not options:
        st.info("Nenhum rascunho ou release disponível.")
        return None
    chosen = st.selectbox(
        "Conteúdo exibido",
        list(options),
        key=VIEW_KEY,
        format_func=lambda key: options[key][0] if key in options else key,
    )
    view = options[chosen][1]
    if view.kind != "draft" or view.draft_id is None:
        return view
    return _pinned_draft_view(ws, view.draft_id)


def _pinned_draft_view(ws: CatalogWorkspace, draft_id: str) -> CatalogView:
    """Revisão que a pessoa está vendo; só avança por recarga ou pela própria ação.

    Assim uma edição concorrente é detectada pelo serviço (revisão esperada) em vez de
    ser absorvida silenciosamente no reenvio do formulário.
    """
    current = next(d for d in ws.list_drafts() if d.draft_id == draft_id)
    key = f"{SEEN_PREFIX}{draft_id}"
    if key not in st.session_state:
        st.session_state[key] = current.revision
    seen = int(st.session_state[key])
    if seen != current.revision:
        st.warning(
            f"O rascunho mudou: você está vendo a r{seen}, a atual é a r{current.revision}. "
            "Ações sobre a revisão vista serão recusadas sem efeito; seus campos digitados "
            "continuam preenchidos."
        )
        if st.button("Recarregar revisão atual", key=f"catalog_reload_{draft_id}"):
            st.session_state[key] = current.revision
            seen = current.revision
    return CatalogView(kind="draft", draft_id=draft_id, revision=seen)


def _filter(label: str, values: tuple[str, ...], key: str) -> str | None:
    picked = st.selectbox(label, [ALL, *values], key=key)
    return None if picked == ALL else picked


def render_table_tab(ws: CatalogWorkspace, view: CatalogView | None) -> None:
    """Tabela filtrável de usos e o detalhe da linha escolhida."""
    if view is None:
        return
    try:
        options = ws.filter_options(view)
        cols = st.columns(4)
        with cols[0]:
            source = _filter("Fonte", options.sources, "catalog_filter_source")
        with cols[1]:
            entity = _filter("Classe IFC", options.entity_classes, "catalog_filter_class")
        with cols[2]:
            profile = _filter("Perfil", options.profiles, "catalog_filter_profile")
        with cols[3]:
            state = _filter("Estado cadastral", options.states, "catalog_filter_state")
        rows = ws.rows(
            view, RowFilters(source=source, entity_class=entity, profile=profile, state=state)
        )
    except WorkspaceError as error:
        show_error(error)
        return
    st.dataframe(
        [
            {
                "Campo": r.field_name,
                "Conjunto": r.set_name or "—",
                "Conceito": f"{r.concept_code} ({r.concept_label})",
                "Classes": ", ".join(r.entity_classes),
                "Schemas": ", ".join(r.schemas),
                "Perfis": ", ".join(r.profiles) or "—",
                "Fontes": ", ".join(r.sources) or "—",
                "Estado cadastral": r.lifecycle,
                "Portador": f"{r.carrier_kind} ({r.carrier_status})",
                "Capacidade": r.capability.state,
                "Escrita IFC": "habilitada" if r.write_enabled else "desligada",
                "Usos do conceito": r.concept_shared_by,
            }
            for r in rows
        ],
        hide_index=True,
        width="stretch",
    )
    st.caption(f"{len(rows)} uso(s) exibido(s). Conceito e uso (binding) aparecem separados.")
    if not rows:
        return
    labels = {f"{r.field_name} · {', '.join(r.entity_classes)} · {r.binding_id}": r for r in rows}
    chosen = st.selectbox("Detalhar uso", list(labels), key=ROW_KEY)
    _render_detail(ws, view, labels[chosen].binding_id)
    with st.expander("Operações implementadas no código instalado"):
        st.dataframe(
            [
                {"Operação": c.operation_id, "Estado": c.state, "Motivo": c.reason}
                for c in ws.operations()
            ],
            hide_index=True,
        )


def _render_detail(ws: CatalogWorkspace, view: CatalogView, binding_id: str) -> None:
    try:
        detail = ws.detail(view, binding_id)
    except WorkspaceError as error:
        show_error(error)
        return
    row = detail.row
    left, right = st.columns(2)
    with left:
        st.subheader("Conceito")
        safe_text("ID", row.concept_id)
        safe_text("Código", row.concept_code)
        safe_text("Rótulo", row.concept_label)
        safe_text("Definição", " | ".join(detail.concept_definition))
        safe_text("Tipo lógico", detail.concept_logical_type)
        safe_text("Dimensão", detail.concept_dimension)
        safe_text("Unidade", detail.unit)
        safe_text("Domínio", ", ".join(detail.value_set))
        safe_text("Outros usos do mesmo conceito", ", ".join(detail.sibling_bindings))
    with right:
        st.subheader("Uso (binding)")
        safe_text("ID", row.binding_id)
        safe_text("Conjunto.campo", f"{row.set_name or '—'}.{row.field_name}")
        safe_text("Portador", f"{row.carrier_kind} ({row.carrier_status})")
        safe_text("Tipo IFC", row.ifc_type)
        safe_text("Escopo", row.scope)
        safe_text("Aplicabilidade", detail.applicability)
        safe_text("Condições", "; ".join(detail.applicability_conditions))
        safe_text("Schemas", ", ".join(row.schemas))
        safe_text(
            "Capacidade",
            f"{row.capability.state} — {row.capability.operation_id or 'sem operação'}",
        )
        safe_text("Motivo da capacidade", row.capability.reason)
        safe_text("Canais admissíveis", ", ".join(detail.policy_channels))
        safe_text("Escrita IFC", "habilitada" if row.write_enabled else "desligada")
    st.subheader("Original (fonte) × reconciliado (catálogo)")
    st.dataframe(
        [
            {
                "Aspecto": p.aspect,
                "Original": " | ".join(p.original) or "—",
                "Reconciliado": p.reconciled or "—",
            }
            for p in detail.original_vs_reconciled
        ],
        hide_index=True,
        width="stretch",
    )
    st.subheader("Aliases")
    st.dataframe(
        [
            {
                "Termo": a.term,
                "Finalidade": a.purpose,
                "Escopo": a.scope,
                "Alvo": a.target,
                "Estado": a.lifecycle,
            }
            for a in detail.aliases
        ],
        hide_index=True,
        width="stretch",
    )
    st.subheader("Proveniência")
    st.dataframe(
        [
            {
                "Assertiva": a.assertion_id,
                "Fonte": a.source_artifact_id,
                "Localização": a.locator,
                "Literal": a.target_literal,
                "Conjunto": a.set_literal or "—",
                "Tipo": a.datatype_literal or "—",
                "Unidade": a.unit_literal or "—",
                "Domínio": a.domain_literal_json or "—",
                "Transcrição": a.transcription_status,
            }
            for a in detail.assertions
        ],
        hide_index=True,
        width="stretch",
    )
    if detail.decisions:
        st.subheader("Decisões de reconciliação")
        st.dataframe(
            [
                {
                    "Código": d.code,
                    "Estado": d.status,
                    "Resumo": d.summary,
                    "Justificativa": d.justification or "—",
                }
                for d in detail.decisions
            ],
            hide_index=True,
        )
    st.subheader("Histórico")
    st.dataframe(
        [
            {
                "UTC": h.at_utc,
                "Operação": h.operation,
                "Ator (declarado)": h.actor,
                "Transição": h.transition,
                "Motivo": h.reason or "—",
            }
            for h in detail.history
        ],
        hide_index=True,
        width="stretch",
    )
    for note in detail.notes:
        st.text(f"Aviso: {note}")
