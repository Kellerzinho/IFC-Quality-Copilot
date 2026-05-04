"""Componente de filtros, busca e ações em lote para issues IFC."""

import streamlit as st

from src.models import Issue, SuggestionSet

_ISSUE_TYPE_OPTIONS: dict[str, str] = {
    "space_unnamed": "Espaço sem nome",
    "pset_missing": "Propriedade ausente",
    "relation_broken": "Relação quebrada",
    "system_unclassified": "Sistema não classificado",
}

_SEVERITY_OPTIONS: dict[str, str] = {
    "high": "Alta",
    "medium": "Média",
    "low": "Baixa",
}

_STATUS_OPTIONS: dict[str, str] = {
    "pending": "Pendente",
    "accepted": "Aceita",
    "edited": "Editada",
    "rejected": "Rejeitada",
    "skipped": "Ignorada",
}

# Chaves de widget — centralizadas para facilitar limpeza
_FILTER_KEYS = ("filter_type", "filter_severity", "filter_status", "search")


# ---------------------------------------------------------------------------
# Dialog de confirmação (deve estar no nível do módulo)
# ---------------------------------------------------------------------------


@st.dialog("Confirmar ação em lote")
def _bulk_confirm_dialog(n: int) -> None:
    """Modal de confirmação antes de aceitar correções em lote."""
    st.warning(
        f"Você está prestes a aceitar **{n} correção(ões)** automaticamente. "
        "As sugestões de alta confiança selecionadas serão escritas no modelo "
        "sem revisão individual. Deseja continuar?"
    )

    col_yes, col_no = st.columns(2)

    with col_yes:
        if st.button(
            "Confirmar",
            type="primary",
            key="bulk_confirm_yes",
            width="stretch",
        ):
            st.session_state.bulk_confirmed = True
            st.rerun()

    with col_no:
        if st.button(
            "Cancelar",
            key="bulk_confirm_no",
            width="stretch",
        ):
            st.session_state.pop("bulk_candidates", None)
            st.rerun()


# ---------------------------------------------------------------------------
# Componente principal
# ---------------------------------------------------------------------------


def render_filters(
    issues: list[tuple[Issue, SuggestionSet]],
) -> list[tuple[Issue, SuggestionSet]]:
    """
    Renderiza filtros, busca e ações em lote.

    Retorna sublista filtrada de issues. Não modifica a lista original.
    """
    type_filter, severity_filter, status_filter = _render_filter_expander()

    search = st.text_input(
        "Buscar por GUID ou nome",
        placeholder="ex: 3AbKuMX... ou 'Sala de Reuniões'",
        key="search",
    )

    filtered = _apply_filters(issues, type_filter, severity_filter, status_filter, search)

    _reset_page_on_filter_change(type_filter, severity_filter, status_filter, search)

    _render_batch_actions(filtered)

    return filtered


# ---------------------------------------------------------------------------
# Filtros
# ---------------------------------------------------------------------------


def _render_filter_expander() -> tuple[list[str], list[str], list[str]]:
    """Renderiza o expander com multiselects e botão de limpeza."""
    with st.expander("Filtros", expanded=False):
        col_type, col_sev, col_status, col_clear = st.columns([2, 2, 2, 1])

        with col_type:
            type_filter: list[str] = st.multiselect(
                "Tipo",
                options=list(_ISSUE_TYPE_OPTIONS.keys()),
                format_func=lambda k: _ISSUE_TYPE_OPTIONS[k],
                key="filter_type",
            )

        with col_sev:
            severity_filter: list[str] = st.multiselect(
                "Severidade",
                options=list(_SEVERITY_OPTIONS.keys()),
                format_func=lambda k: _SEVERITY_OPTIONS[k],
                key="filter_severity",
            )

        with col_status:
            status_filter: list[str] = st.multiselect(
                "Status",
                options=list(_STATUS_OPTIONS.keys()),
                format_func=lambda k: _STATUS_OPTIONS[k],
                key="filter_status",
            )

        with col_clear:
            # Alinha o botão verticalmente com os multiselects
            st.markdown(
                "<div style='padding-top:1.65rem;'></div>",
                unsafe_allow_html=True,
            )
            if st.button("Limpar", key="clear_filters", width="stretch"):
                for k in _FILTER_KEYS:
                    st.session_state.pop(k, None)
                st.session_state.current_page = 0
                st.rerun()

    return type_filter, severity_filter, status_filter


def _apply_filters(
    issues: list[tuple[Issue, SuggestionSet]],
    type_filter: list[str],
    severity_filter: list[str],
    status_filter: list[str],
    search: str,
) -> list[tuple[Issue, SuggestionSet]]:
    """Aplica todos os filtros ativos e retorna sublista."""
    result = issues

    if type_filter:
        result = [(i, s) for i, s in result if i.issue_type in type_filter]

    if severity_filter:
        result = [(i, s) for i, s in result if i.severity in severity_filter]

    if status_filter:
        result = [(i, s) for i, s in result if i.status in status_filter]

    if search.strip():
        q = search.strip().lower()
        result = [
            (i, s)
            for i, s in result
            if q in i.element_guid.lower()
            or (i.element_name and q in i.element_name.lower())
        ]

    return result


def _reset_page_on_filter_change(
    type_filter: list[str],
    severity_filter: list[str],
    status_filter: list[str],
    search: str,
) -> None:
    """Volta para a página 0 quando os filtros ou busca mudam."""
    state = (
        tuple(sorted(type_filter)),
        tuple(sorted(severity_filter)),
        tuple(sorted(status_filter)),
        search.strip(),
    )
    if state != st.session_state.get("_filter_state"):
        st.session_state._filter_state = state
        st.session_state.current_page = 0


# ---------------------------------------------------------------------------
# Ações em lote
# ---------------------------------------------------------------------------


def _render_batch_actions(
    filtered: list[tuple[Issue, SuggestionSet]],
) -> None:
    """
    Renderiza checkbox de seleção em lote e botão de aceite.

    Candidatas elegíveis: issues pendentes com sugestão top-1 de confiança alta.
    Armazena IDs em session_state.bulk_candidates e abre o dialog de confirmação.
    """
    candidates = [
        issue
        for issue, sset in filtered
        if issue.status == "pending"
        and sset.top_suggestion is not None
        and sset.top_suggestion.confidence == "alta"
    ]

    if not candidates:
        return

    n = len(candidates)

    st.divider()

    col_check, col_btn = st.columns([4, 1], vertical_alignment="bottom")

    with col_check:
        select_all = st.checkbox(
            f"Selecionar todas as {n} issues com sugestão top-1 de confiança alta",
            key="bulk_select_all",
        )

    with col_btn:
        accept_clicked = st.button(
            "Aceitar selecionadas",
            disabled=not select_all,
            type="secondary",
            width="stretch",
            key="bulk_accept_btn",
        )

    if accept_clicked and select_all:
        st.session_state.bulk_candidates = [issue.id for issue in candidates]
        _bulk_confirm_dialog(n)
