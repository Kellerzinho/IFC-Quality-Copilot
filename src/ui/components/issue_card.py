"""Componente de card para exibição e decisão sobre issues de qualidade IFC."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import streamlit as st

from src.models import AuditEntry, Issue, SuggestionSet, ValidationResult

if TYPE_CHECKING:
    from src.suggestion_engine.issue_store import IssueStore


_SEVERITY_BADGE: dict[str, str] = {
    "high": "🔴 Alta",
    "medium": "🟡 Média",
    "low": "🟢 Baixa",
}

_STATUS_LABEL: dict[str, str] = {
    "accepted": "Aplicado",
    "edited": "Editado",
    "rejected": "Rejeitado",
    "skipped": "Ignorado",
    "pending": "Pendente",
}

_STATUS_COLOR: dict[str, str] = {
    "accepted": "#22C55E",
    "edited": "#3B82F6",
    "rejected": "#EF4444",
    "skipped": "#94A3B8",
    "pending": "#F59E0B",
}

_SOURCE_BADGE: dict[str, str] = {
    "ready": "🤖 Sugestão do LLM",
    "cached": "💾 Cache",
    "reused": "♻️ Reusado",
    "review_required": "⚠️ Revisar",
}

_SOURCE_BADGE_STYLE: dict[str, str] = {
    "ready": "background:#1E3A5F20; color:#93C5FD; border: 1px solid #1E3A5F60;",
    "cached": "background:#0F4C5C30; color:#67E8F9; border: 1px solid #155E7560;",
    "reused": "background:#3B0A4530; color:#D8B4FE; border: 1px solid #6B21A860;",
    "review_required": "background:#52341230; color:#FBBF24; border: 1px solid #92400E60;",
}

_CUSTOM_OPTION_LABEL = "Outro (valor customizado)"


def render_issue_card(
    issue: Issue,
    suggestion_set: SuggestionSet | None,
    index: int,
    status: str = "ready",
    issue_store: IssueStore | None = None,
    audit_entry: AuditEntry | None = None,
    validation_result: ValidationResult | None = None,
) -> dict | None:
    """
    Renderiza um card de issue com comportamento dependente do status.

    Parâmetro `status` controla a renderização:
    - "ready": card completo com sugestões e botões de decisão
    - "processing": card com borda amarela e indicador de carregamento
    - "queued": card com borda cinza e posição na fila
    - "failed": card com borda vermelha, mensagem de erro e botão de retry

    Issues com issue.status "accepted" ou "edited" são sempre renderizadas
    como card colapsado com badge verde, independente do `status`.

    Retorna dict com decisão se o usuário agiu, None caso contrário.
    Formato: {"decision": "accepted"|"edited"|"skipped", "value": Any, "suggestion_index": int | None}
    """
    # Issues já resolvidas com aprovação: card colapsado
    if issue.status in ("accepted", "edited"):
        _render_collapsed_card(issue, index, validation_result)
        return None

    if status == "processing":
        _render_processing_card(issue, index)
        return None

    if status == "queued":
        _render_queued_card(issue, index)
        return None

    if status == "failed":
        _render_failed_card(issue, index, suggestion_set, issue_store)
        return None

    # "ready": renderização completa
    with st.container(border=True):
        _render_header(issue, index, status)
        _render_issue_focus(issue)

        if issue.status != "pending":
            _render_resolved_summary(issue, audit_entry)
            return None

        return _render_pending_controls(issue, suggestion_set)


# ---------------------------------------------------------------------------
# Cards de estado especial
# ---------------------------------------------------------------------------


def _render_collapsed_card(
    issue: Issue,
    index: int,
    validation_result: ValidationResult | None = None,
) -> None:
    """Renderiza card compacto para issue aceita ou editada pelo usuário."""
    color = _STATUS_COLOR.get(issue.status, "#22C55E")
    label = _STATUS_LABEL.get(issue.status, issue.status)
    value_part = (
        f" &mdash; <span style='color:#CBD5E1;'>{issue.resolution_value}</span>"
        if issue.resolution_value is not None
        else ""
    )
    timestamp_part = ""
    if issue.resolved_at:
        timestamp_part = (
            f"<span style='color:#475569; font-size:0.72rem; margin-left:0.5rem;'>"
            f"{issue.resolved_at.strftime('%d/%m %H:%M')}</span>"
        )

    st.markdown(
        f'<div class="state-card" style="border-color:{color}; background:{color}0D;">'
        f'<div style="display:flex; align-items:center; gap:0.5rem; flex-wrap:wrap;">'
        f'<span style="color:#64748B; font-size:0.7rem; text-transform:uppercase; '
        f'letter-spacing:0.08em;">ISSUE #{index}</span>'
        f'<span style="color:#94A3B8; font-size:0.82rem; font-family:\'Fira Code\',monospace;">'
        f'{issue.element_class}</span>'
        f'<span style="font-size:0.88rem; font-weight:600; color:#CBD5E1;">'
        f'{issue.type_label}</span>'
        f'<span class="status-badge" style="background:{color}20; color:{color};">'
        f'{label}</span>'
        f'{value_part}{timestamp_part}'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    _render_post_validation_state(validation_result)


def _render_processing_card(issue: Issue, index: int) -> None:
    """Renderiza card com indicador de processamento (borda amarela)."""
    st.markdown(
        f'<div class="state-card" style="border-color:#F59E0B; background:#F59E0B0D;">'
        f'<div style="display:flex; justify-content:space-between; align-items:flex-start;">'
        f'<div>'
        f'<p class="issue-header-label">ISSUE #{index}</p>'
        f'<p class="issue-title">{issue.type_label}</p>'
        f'<p class="issue-element-ref" style="margin-top:0.25rem;">'
        f'{issue.element_class} #{issue.short_guid}</p>'
        f'</div>'
        f'<span class="severity-badge">{_SEVERITY_BADGE[issue.severity]}</span>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    with st.spinner(f"Gerando sugestões para {issue.type_label}..."):
        pass


def _render_queued_card(issue: Issue, index: int) -> None:
    """Renderiza card na fila de processamento (borda cinza)."""
    st.markdown(
        f'<div class="state-card" style="border-color:#475569; background:#47556910;">'
        f'<div style="display:flex; justify-content:space-between; align-items:flex-start;">'
        f'<div>'
        f'<p class="issue-header-label">ISSUE #{index}</p>'
        f'<p class="issue-title" style="color:#94A3B8;">{issue.type_label}</p>'
        f'<p class="issue-element-ref" style="margin-top:0.25rem;">'
        f'{issue.element_class} #{issue.short_guid}</p>'
        f'</div>'
        f'<div style="text-align:right;">'
        f'<span class="severity-badge">{_SEVERITY_BADGE[issue.severity]}</span>'
        f'<div style="color:#64748B; font-size:0.75rem; margin-top:0.3rem;">'
        f'&#x23F3; Na fila (posição #{index})</div>'
        f'</div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _render_failed_card(
    issue: Issue,
    index: int,
    suggestion_set: SuggestionSet | None,
    issue_store: IssueStore | None,
) -> None:
    """Renderiza card de falha com mensagem de erro e botão para tentar novamente."""
    error_msg = (
        suggestion_set.error
        if suggestion_set and suggestion_set.error
        else "Erro desconhecido ao gerar sugestão."
    )
    st.markdown(
        f'<div class="state-card" style="border-color:#EF4444; background:#EF44440D;">'
        f'<div style="display:flex; justify-content:space-between; align-items:flex-start;">'
        f'<div style="flex:1;">'
        f'<p class="issue-header-label">ISSUE #{index}</p>'
        f'<p class="issue-title">{issue.type_label}</p>'
        f'<p class="issue-element-ref" style="margin-top:0.25rem;">'
        f'{issue.element_class} #{issue.short_guid}</p>'
        f'<p style="color:#FCA5A5; font-size:0.8rem; margin-top:0.4rem;">'
        f'Falha: {error_msg}</p>'
        f'</div>'
        f'<span class="severity-badge">{_SEVERITY_BADGE[issue.severity]}</span>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    if st.button(
        "Tentar novamente",
        key=f"issue_{issue.id}_retry",
        type="secondary",
    ):
        if issue_store is not None:
            issue_store.requeue(issue.id)
            st.rerun()


# ---------------------------------------------------------------------------
# Partes internas do card completo (ready)
# ---------------------------------------------------------------------------


def _render_header(issue: Issue, index: int, status: str) -> None:
    """Renderiza header com número do issue, tipo, badge de fonte e severidade/status."""
    col_left, col_right = st.columns([3, 1], vertical_alignment="center")

    with col_left:
        source_badge_html = ""
        if status in _SOURCE_BADGE:
            badge_label = _SOURCE_BADGE[status]
            badge_style = _SOURCE_BADGE_STYLE[status]
            source_badge_html = (
                f'<span class="source-badge" style="{badge_style}">'
                f'{badge_label}</span>'
            )

        st.markdown(
            f'<p class="issue-header-label">ISSUE #{index}</p>'
            f'<p class="issue-title">{issue.type_label}{source_badge_html}</p>',
            unsafe_allow_html=True,
        )

    with col_right:
        severity_html = (
            f'<span class="severity-badge">'
            f'{_SEVERITY_BADGE[issue.severity]}</span>'
        )
        status_html = ""
        if issue.status != "pending":
            color = _STATUS_COLOR.get(issue.status, "#94A3B8")
            label = _STATUS_LABEL.get(issue.status, issue.status)
            status_html = (
                f'<span class="status-badge" style="background:{color}20; color:{color};">'
                f'{label}</span>'
            )
        st.markdown(severity_html + status_html, unsafe_allow_html=True)


def _render_issue_focus(issue: Issue) -> None:
    """Renderiza apenas o foco da análise: elemento e propriedade/requisito avaliado."""
    element_name = issue.element_name or "Sem nome"
    target = _issue_target_label(issue)
    target_html = (
        f'<div class="context-item">'
        f'<div class="context-key">Propriedade avaliada</div>'
        f'<div class="context-val">{target}</div>'
        f'</div>'
        if target
        else ""
    )
    st.markdown(
        f'<div class="context-grid">'
        f'<div class="context-item">'
        f'<div class="context-key">Nome</div>'
        f'<div class="context-val">{element_name}</div>'
        f'</div>'
        f'{target_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


def _issue_target_label(issue: Issue) -> str:
    """Extrai o campo principal avaliado sem expor o contexto técnico completo."""
    context = issue.context or {}
    for key in (
        "check_property",
        "property_name",
        "quantity_name",
        "expected_relation",
        "classification_system",
    ):
        value = context.get(key)
        if value not in (None, ""):
            return str(value)
    return issue.type_label


def _render_resolved_summary(issue: Issue, audit_entry: AuditEntry | None = None) -> None:
    """Renderiza resumo quando o issue foi rejeitado ou ignorado."""
    color = _STATUS_COLOR.get(issue.status, "#94A3B8")
    label = _STATUS_LABEL.get(issue.status, issue.status)
    value_part = (
        f"<br><strong>Valor aplicado:</strong> {issue.resolution_value}"
        if issue.resolution_value is not None
        else ""
    )
    resolved_str = ""
    if issue.resolved_at:
        resolved_str = (
            f"<br><span style='color:#64748B;font-size:0.75rem;'>"
            f"{issue.resolved_at.strftime('%d/%m/%Y %H:%M')}</span>"
        )

    st.markdown(
        f'<div class="resolution-box" style="border-color:{color};">'
        f'<strong style="color:{color};">{label}</strong>'
        f'{value_part}{resolved_str}'
        f'</div>',
        unsafe_allow_html=True,
    )
    if audit_entry is not None:
        _render_validation_box(audit_entry)


def _render_pending_controls(
    issue: Issue,
    suggestion_set: SuggestionSet | None,
) -> dict | None:
    """
    Renderiza controles de decisão para issues pendentes.

    Retorna dict com decisão ou None se nenhuma ação foi tomada.
    """
    st.markdown("---")

    if suggestion_set is None:
        st.warning("Sugestões ainda não disponíveis.")
        return None

    if suggestion_set.error:
        st.warning(f"Não foi possível gerar sugestões: {suggestion_set.error}")

    suggestion_set.suggestions = sorted(
        suggestion_set.suggestions,
        key=lambda suggestion: suggestion.confidence_order,
    )
    radio_options, option_meta = _build_radio_options(suggestion_set)

    selected = st.radio(
        "Selecione a correção",
        options=radio_options,
        key=f"issue_{issue.id}_radio",
        label_visibility="collapsed",
    )

    selected_index = radio_options.index(selected) if selected in radio_options else 0
    is_custom = selected == _CUSTOM_OPTION_LABEL

    _render_selection_details(issue, suggestion_set, selected_index, is_custom, option_meta)

    custom_value: str = ""
    if is_custom:
        custom_value = st.text_input(
            "Valor customizado",
            placeholder="Digite o valor a aplicar...",
            key=f"issue_{issue.id}_custom_input",
        )

    return _render_action_buttons(issue, suggestion_set, selected_index, is_custom, custom_value)


def _build_radio_options(
    suggestion_set: SuggestionSet,
) -> tuple[list[str], list[dict]]:
    """
    Constrói lista de opções para o radio e metadados associados.

    Retorna (labels, metadados) onde metadados contém normative_ref por opção.
    """
    options: list[str] = []
    meta: list[dict] = []

    for sug in suggestion_set.suggestions:
        normref_part = ""
        if sug.normative_ref:
            normref_part = f" [{sug.normative_ref}]"
        label = f"{sug.label} (confiança: {sug.confidence_emoji} {sug.confidence}){normref_part}"
        options.append(label)
        meta.append({"normative_ref": sug.normative_ref})

    if suggestion_set.allow_custom or not suggestion_set.has_suggestions:
        options.append(_CUSTOM_OPTION_LABEL)
        meta.append({"normative_ref": None})

    return options, meta


def _render_selection_details(
    issue: Issue,
    suggestion_set: SuggestionSet,
    selected_index: int,
    is_custom: bool,
    option_meta: list[dict],
) -> None:
    """Exibe justificativa e referência normativa da opção selecionada."""
    if is_custom or not suggestion_set.has_suggestions:
        return

    if selected_index < len(suggestion_set.suggestions):
        sug = suggestion_set.suggestions[selected_index]

        normref_html = ""
        if sug.normative_ref:
            normref_html = f'<span class="normref-badge">{sug.normative_ref}</span>'

        st.markdown(
            f'<div style="margin: 0.4rem 0 0.6rem 0; padding: 0.5rem 0.75rem; '
            f'background: #0F172A; border-radius: 6px; font-size: 0.82rem; color: #94A3B8;">'
            f'{sug.justification}{normref_html}'
            f'</div>',
            unsafe_allow_html=True,
        )
        return


def _render_suggestion_grounding_rows(suggestion_set: SuggestionSet) -> None:
    """Exibe badges de proveniÃªncia para cada sugestÃ£o do radio group."""
    for idx, suggestion in enumerate(suggestion_set.suggestions, start=1):
        badges = _build_grounding_badges(suggestion.bsdd_uri, suggestion.ids_requirement_id)
        if not badges:
            continue

        st.markdown(
            f"<div style='margin:-0.15rem 0 0.45rem 2rem; font-size:0.76rem; color:#94A3B8;'>"
            f"<span style='margin-right:0.45rem;'>OpÃ§Ã£o {idx}</span>{''.join(badges)}"
            f"</div>",
            unsafe_allow_html=True,
        )


def _render_selected_suggestion_metadata(suggestion) -> None:
    """Exibe detalhes de grounding da sugestÃ£o selecionada."""
    details: list[str] = []
    if suggestion.bsdd_uri:
        details.append(
            "<div style='margin-top:0.25rem;'>"
            "<span style='color:#7DD3FC; font-size:0.76rem; margin-right:0.35rem;'>bSDD URI:</span>"
            f"<a href='{suggestion.bsdd_uri}' target='_blank' "
            "style='color:#BAE6FD; text-decoration:none;'>"
            f"{suggestion.bsdd_uri}</a></div>"
        )
    if details:
        st.markdown("".join(details), unsafe_allow_html=True)


def _build_grounding_badges(bsdd_uri: str | None, ids_requirement_id: str | None) -> list[str]:
    """Monta badges inline de grounding para a sugestÃ£o."""
    badges: list[str] = []
    if bsdd_uri:
        badges.append(
            f"<a href='{bsdd_uri}' target='_blank' title='{bsdd_uri}' "
            "style='display:inline-block; margin-right:0.35rem; padding:0.12rem 0.5rem; "
            "border-radius:999px; border:1px solid #0EA5E980; background:#0EA5E920; "
            "color:#7DD3FC; text-decoration:none; font-weight:600;'>bSDD</a>"
        )
    return badges


def _render_suggestion_grounding_metadata(suggestion_set: SuggestionSet) -> None:
    """Exibe badges de grounding para cada opcao sem depender de CSS global."""
    for idx, suggestion in enumerate(suggestion_set.suggestions, start=1):
        badges = _build_grounding_badges(suggestion.bsdd_uri, suggestion.ids_requirement_id)
        if not badges:
            continue

        st.markdown(
            f"<div style='margin:-0.15rem 0 0.45rem 2rem; font-size:0.76rem; color:#94A3B8;'>"
            f"<span style='margin-right:0.45rem;'>Opcao {idx}</span>{''.join(badges)}"
            f"</div>",
            unsafe_allow_html=True,
        )


def _render_post_validation_state(validation_result: ValidationResult | None) -> None:
    """Exibe o resultado de pos-validacao da correcao aplicada."""
    if validation_result is None or validation_result.status == "skip":
        return

    if validation_result.status == "pass":
        st.success("\u2713 Validado")
        return

    errors = validation_result.errors or [*validation_result.schema_errors, *validation_result.ids_errors]
    if errors:
        st.error("\u2717 Falha: " + ", ".join(errors))
    else:
        st.error("\u2717 Falha de validacao")


def _render_provenance(
    issue: Issue,
    suggestion_set: SuggestionSet | None,
    audit_entry: AuditEntry | None,
) -> None:
    """Exibe grounding, proveniência e pós-validação quando disponíveis."""
    top = suggestion_set.top_suggestion if suggestion_set is not None else None
    bsdd_uri = None

    if audit_entry is not None:
        bsdd_uri = audit_entry.bsdd_uri
    elif top is not None:
        bsdd_uri = top.bsdd_uri

    details: list[str] = []
    if bsdd_uri:
        details.append(
            f"<a class='prov-chip' href='{bsdd_uri}' target='_blank' "
            f"style='text-decoration:none;'>bSDD</a>"
        )

    if details:
        st.markdown(
            f"<div class='prov-row'>{''.join(details)}</div>",
            unsafe_allow_html=True,
        )


def _render_validation_box(audit_entry: AuditEntry) -> None:
    """Exibe o resultado da pós-validação da correção aplicada."""
    color_map = {"pass": "#22C55E", "fail": "#EF4444", "skip": "#94A3B8"}
    label_map = {"pass": "Pós-validação aprovada", "fail": "Pós-validação reprovada", "skip": "Pós-validação não executada"}
    color = color_map.get(audit_entry.post_validation, "#94A3B8")
    label = label_map.get(audit_entry.post_validation, audit_entry.post_validation)
    st.markdown(
        f"<div class='validation-box' style='border-color:{color}; color:{color};'>{label}</div>",
        unsafe_allow_html=True,
    )


def _render_post_validation_result(validation_result: ValidationResult | None) -> None:
    """Exibe o resultado da pÃ³s-validaÃ§Ã£o quando disponÃ­vel."""
    if validation_result is None or validation_result.status == "skip":
        return

    if validation_result.status == "pass":
        st.success("✓ ValidaÃ§Ã£o pÃ³s-correÃ§Ã£o: OK")
        return

    errors = validation_result.errors or [*validation_result.schema_errors, *validation_result.ids_errors]
    if errors:
        st.error("✗ Falha: " + ", ".join(errors))
    else:
        st.error("✗ Falha de validaÃ§Ã£o")


def _render_action_buttons(
    issue: Issue,
    suggestion_set: SuggestionSet,
    selected_index: int,
    is_custom: bool,
    custom_value: str,
) -> dict | None:
    """
    Renderiza botões de ação e retorna decisão se algum foi clicado.

    Retorna dict ou None.
    """
    col_apply, col_skip, col_later = st.columns(3)

    apply_disabled = is_custom and not custom_value.strip()

    with col_apply:
        apply_clicked = st.button(
            "Aplicar",
            type="primary",
            key=f"issue_{issue.id}_apply",
            disabled=apply_disabled,
            width="stretch",
        )

    with col_skip:
        skip_clicked = st.button(
            "Pular",
            key=f"issue_{issue.id}_skip",
            width="stretch",
        )

    with col_later:
        later_clicked = st.button(
            "Revisão posterior",
            key=f"issue_{issue.id}_later",
            width="stretch",
        )

    if apply_clicked:
        return _build_apply_result(suggestion_set, selected_index, is_custom, custom_value)

    if skip_clicked:
        return {"decision": "skipped", "value": None, "suggestion_index": None}

    if later_clicked:
        return {"decision": "skipped", "value": None, "suggestion_index": None}

    return None


def _build_apply_result(
    suggestion_set: SuggestionSet,
    selected_index: int,
    is_custom: bool,
    custom_value: str,
) -> dict[str, Any]:
    """Monta o dict de resultado para a ação 'Aplicar'."""
    if is_custom:
        return {
            "decision": "edited",
            "value": custom_value.strip(),
            "suggestion_index": None,
        }

    sug = suggestion_set.get_by_index(selected_index)
    if sug is None:
        return {
            "decision": "edited",
            "value": custom_value.strip(),
            "suggestion_index": None,
        }

    return {
        "decision": "accepted",
        "value": sug.value,
        "suggestion_index": selected_index,
    }
