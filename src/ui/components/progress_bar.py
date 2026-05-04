"""Componente de barra de progresso para o pipeline de qualidade IFC."""

import streamlit as st


def render_progress(progress: dict) -> None:
    """
    Renderiza barra de progresso do pipeline.

    Parâmetro progress deve conter os campos retornados por
    pipeline.get_progress(), opcionalmente enriquecidos com
    model_name, accepted, edited, rejected, skipped.
    """
    model_name: str = progress.get("model_name", "")
    total: int = progress.get("total", 0)
    resolved: int = progress.get("resolved", 0)
    pending: int = progress.get("pending", total - resolved)
    accepted: int = progress.get("accepted", 0)
    edited: int = progress.get("edited", 0)
    skipped: int = progress.get("skipped", 0)
    percentage: float = progress.get("percentage", 0.0)

    # --- Linha de texto descritiva ---
    parts: list[str] = []
    if model_name:
        parts.append(f"**{model_name}**")
    parts.append(f"{total} issues")
    parts.append(f"{resolved} resolvidas")

    st.markdown(" | ".join(parts))

    # --- Barra de progresso nativa ---
    pct_norm = max(0.0, min(1.0, percentage / 100.0))
    label = f"{percentage:.0f}% concluído"
    st.progress(pct_norm, text=label)

    # --- Métricas em 4 colunas ---
    col_acc, col_edit, col_skip, col_pend = st.columns(4)

    with col_acc:
        st.metric(
            label="✅ Aceitas",
            value=accepted,
            delta=None,
        )

    with col_edit:
        st.metric(
            label="✏️ Editadas",
            value=edited,
            delta=None,
        )

    with col_skip:
        st.metric(
            label="⏭️ Puladas",
            value=skipped,
            delta=None,
        )

    with col_pend:
        st.metric(
            label="⏳ Pendentes",
            value=pending,
            delta=None,
        )
