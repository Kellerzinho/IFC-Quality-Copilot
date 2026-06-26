"""Componente de ações em lote para issues IFC."""

import streamlit as st

from src.models import Issue, SuggestionSet

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
    Renderiza ações em lote e retorna todas as issues.

    A revisão deve sempre mostrar a lista completa; filtros e busca foram
    desativados para evitar que issues fiquem ocultas durante a conferência.
    """
    _render_batch_actions(issues)
    return issues


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
