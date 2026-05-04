"""Componente de dashboard com visual editorial para o IFC Quality Copilot."""

from __future__ import annotations

import os
import tempfile

import plotly.graph_objects as go
import streamlit as st
from loguru import logger

from src.ifc_analyzer.analyzer import IFCAnalyzer
from src.models import DiagnosticReport, Issue, ReadinessScore
from src.pipeline import QualityPipeline
from src.profiles.registry import create_default_registry

_COLOR_BY_TYPE: dict[str, str] = {
    "space_unnamed": "#63D2FF",
    "pset_missing": "#F6A93B",
    "relation_broken": "#FF6B6B",
    "system_unclassified": "#43D17F",
    "quantity_missing": "#A0E85A",
    "classification_missing": "#4FB8C6",
    "material_unmapped": "#F7C66D",
    "asset_unidentified": "#FF8E72",
    "thermal_incomplete": "#8CE1C4",
}

_LABEL_BY_TYPE: dict[str, str] = {
    "space_unnamed": "Espaço sem nome",
    "pset_missing": "Propriedade ausente",
    "relation_broken": "Relação quebrada",
    "system_unclassified": "Sistema não classificado",
    "quantity_missing": "Quantidade ausente",
    "classification_missing": "Classificação ausente",
    "material_unmapped": "Material não mapeado",
    "asset_unidentified": "Equipamento sem ID",
    "thermal_incomplete": "Dados térmicos incompletos",
}

_COLOR_BY_SEVERITY: dict[str, str] = {
    "high": "#FF6B6B",
    "medium": "#F6A93B",
    "low": "#43D17F",
}

_LABEL_BY_SEVERITY: dict[str, str] = {
    "high": "Alta",
    "medium": "Média",
    "low": "Baixa",
}

_COLOR_BY_STATUS: dict[str, str] = {
    "accepted": "#43D17F",
    "edited": "#63D2FF",
    "rejected": "#FF6B6B",
    "skipped": "#94AEBE",
    "pending": "#F6A93B",
}

_LABEL_BY_STATUS: dict[str, str] = {
    "accepted": "Aceitas",
    "edited": "Editadas",
    "rejected": "Rejeitadas",
    "skipped": "Puladas",
    "pending": "Pendentes",
}

_COLOR_BY_READINESS: dict[str, str] = {
    "ready": "#43D17F",
    "partially_ready": "#F6A93B",
    "not_ready": "#FF6B6B",
}

_LABEL_BY_READINESS: dict[str, str] = {
    "ready": "Pronto",
    "partially_ready": "Parcialmente pronto",
    "not_ready": "Não pronto",
}

_SEVERITY_ORDER = ("high", "medium", "low")
_STATUS_ORDER = ("accepted", "edited", "rejected", "skipped", "pending")

_LAYOUT_BASE: dict = {
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor": "rgba(0,0,0,0)",
    "font": {"color": "#F3F8FB", "family": "Sora, sans-serif", "size": 12},
    "margin": {"t": 56, "b": 24, "l": 20, "r": 20},
    "legend": {
        "bgcolor": "rgba(255,255,255,0.02)",
        "bordercolor": "rgba(130,172,191,0.18)",
        "borderwidth": 1,
        "font": {"size": 11},
    },
}

def render_dashboard(pipeline: QualityPipeline) -> None:
    """Renderiza dashboard principal do pipeline."""
    report = pipeline.report
    if report is None:
        st.info("Execute o diagnóstico para visualizar o dashboard.")
        return

    issues = report.issues
    if not issues:
        st.info("Nenhuma issue encontrada no modelo.")
        return

    _render_dashboard_hero(pipeline, report)

    tab_cockpit, tab_readiness, tab_audit = st.tabs(["Cockpit", "Readiness", "Auditoria"])

    with tab_cockpit:
        _render_cockpit_tab(pipeline, report)

    with tab_readiness:
        _render_readiness_tab(pipeline)

    with tab_audit:
        _render_auditoria_tab(pipeline)


def _render_dashboard_hero(pipeline: QualityPipeline, report: DiagnosticReport) -> None:
    """Renderiza hero principal do dashboard."""
    counts = _compute_issue_counts(report.issues)
    total = report.total_issues
    resolved = total - counts["pending"]
    resolution_rate = (resolved / total * 100) if total else 0.0
    high_share = (counts["high"] / total * 100) if total else 0.0
    selected_profile = pipeline.profile.name if pipeline.profile is not None else "Diagnóstico genérico"
    city = pipeline.building_context.get("city") or "Cidade não informada"
    state = pipeline.building_context.get("state") or "UF"
    st.markdown(
        f"""
        <section class="app-hero">
            <div class="hero-kicker">Instituto Militar de Engenharia</div>
            <h2 class="hero-title">{report.model_name}</h2>
            <p class="hero-subtitle">
                Painel de comando para inspecao de qualidade BIM com foco em disciplina,
                rastreabilidade e leitura rapida do estado tecnico do modelo.
            </p>
            <div class="hero-chip-row">
                <span class="hero-chip">{report.total_elements} elementos</span>
                <span class="hero-chip">{total} issues detectadas</span>
                <span class="hero-chip">{resolution_rate:.0f}% revisado</span>
                <span class="hero-chip">{high_share:.0f}% criticas</span>
                <span class="hero-chip">{selected_profile}</span>
                <span class="hero-chip">{city} - {state}</span>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div class="dashboard-panel">
            <p class="dashboard-panel-title">Diretriz operacional</p>
            <p class="dashboard-panel-subtitle">
                Priorize backlog critico, valide a proveniencia das sugestoes e consolide
                apenas correcoes aprovadas pelo engenheiro responsavel.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )



def _render_cockpit_tab(pipeline: QualityPipeline, report: DiagnosticReport) -> None:
    """Renderiza a visão geral moderna do dashboard."""
    issues = report.issues
    counts = _compute_issue_counts(issues)
    total = report.total_issues
    resolved = total - counts["pending"]
    resolution_rate = (resolved / total * 100) if total else 0.0
    high_share = (counts["high"] / total * 100) if total else 0.0
    review_balance = counts["accepted"] + counts["edited"]

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        _render_kpi_card("Issues críticas", counts["high"], f"{high_share:.0f}% do backlog atual", "#FF6B6B")
    with col2:
        _render_kpi_card("Resolução", f"{resolution_rate:.0f}%", f"{resolved} de {total} revisadas", "#63D2FF")
    with col3:
        _render_kpi_card("Aplicações", review_balance, "aceitas ou ajustadas pelo engenheiro", "#43D17F")
    with col4:
        _render_kpi_card("Modelo", report.total_elements, "elementos inspecionados no diagnóstico", "#F6A93B")

    col_story, col_inventory = st.columns([1.7, 1], gap="large")
    with col_story:
        _render_panel_header(
            "Leitura executiva",
            "Os pontos que mais pesam na qualidade atual e no esforço de saneamento.",
        )
        stat_cols = st.columns(3)
        with stat_cols[0]:
            _render_stat_card(
                "Maior concentração",
                _format_top_issue_type(report.issues_by_type),
                "Tipo de issue dominante neste modelo.",
            )
        with stat_cols[1]:
            _render_stat_card(
                "Pendentes",
                counts["pending"],
                "Itens ainda sem decisão humana aplicada.",
            )
        with stat_cols[2]:
            _render_stat_card(
                "Rejeições",
                counts["rejected"],
                "Correções recusadas durante a revisão.",
            )
    with col_inventory:
        _render_panel_header("Inventário BIM", "Volume de entidades principais presentes no IFC.")
        inv1, inv2 = st.columns(2)
        with inv1:
            _render_stat_card("Espaços", report.total_spaces, "Mapeados para leitura funcional.")
            _render_stat_card("Portas", report.total_doors, "Aberturas avaliadas.")
        with inv2:
            _render_stat_card("Paredes", report.total_walls, "Componentes verticais analisados.")
            _render_stat_card("Lajes", report.total_slabs, "Superfícies horizontais verificadas.")
        _render_stat_card("Janelas", report.total_windows, "Fachada e vedações transparentes.")

    col_type, col_severity = st.columns(2, gap="large")
    with col_type:
        _render_panel_header("Composição por tipo", "Onde a maior parte da dívida de modelagem está concentrada.")
        st.plotly_chart(_pie_by_type(issues), width="stretch")
    with col_severity:
        _render_panel_header("Pressão por severidade", "Risco operacional distribuído por criticidade.")
        st.plotly_chart(_pie_by_severity(issues), width="stretch")

    col_matrix, col_status = st.columns(2, gap="large")
    with col_matrix:
        _render_panel_header("Mapa de risco", "Combinação entre severidade e tipo para detectar hotspots.")
        st.plotly_chart(_stacked_severity_by_type(issues), width="stretch")
    with col_status:
        _render_panel_header("Fluxo de revisão", "Como a triagem humana está evoluindo no pipeline.")
        st.plotly_chart(_bar_by_status(issues), width="stretch")


def _render_readiness_tab(pipeline: QualityPipeline) -> None:
    """Renderiza aba de readiness com gauge, comparativo e cobertura."""
    report = pipeline.report
    if report is None:
        return

    _render_note(
        "Readiness mede o quanto o modelo está pronto para um uso específico. "
        "O score combina cobertura das verificações com o número de issues bloqueantes abertas."
    )

    if pipeline.profile is not None:
        _render_readiness_gauge(pipeline)
    else:
        st.markdown(
            """
            <div class="dashboard-panel">
                <p class="dashboard-panel-title">Perfil não selecionado</p>
                <p class="dashboard-panel-subtitle">
                    Escolha um perfil de readiness na sidebar para ver uma leitura de prontidão orientada ao uso.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.divider()
    _render_panel_header("Comparativo de perfis", "O mesmo modelo avaliado sob diferentes critérios de prontidão.")
    _render_readiness_comparison(pipeline, report.issues)

    st.divider()
    _render_panel_header("Cobertura por perfil", "Quais tipos de problema afetam cada cenário de uso do modelo.")
    _render_profile_coverage(report.issues)


def _render_readiness_gauge(pipeline: QualityPipeline) -> None:
    """Renderiza o score do perfil ativo."""
    try:
        score = pipeline.compute_readiness()
    except Exception as exc:
        st.warning(f"Não foi possível calcular o score: {exc}")
        return

    gauge_color = _COLOR_BY_READINESS[score.status]
    status_label = _LABEL_BY_READINESS[score.status]
    blocking_issues = _get_blocking_issues(pipeline)

    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=score.score_percent,
            number={"suffix": "%", "font": {"size": 34, "color": "#F3F8FB"}},
            title={"text": score.profile_name, "font": {"size": 15, "color": "#94AEBE"}},
            gauge={
                "axis": {
                    "range": [0, 100],
                    "tickcolor": "#5D7787",
                    "tickfont": {"color": "#94AEBE"},
                },
                "bar": {"color": gauge_color, "thickness": 0.28},
                "bgcolor": "rgba(255,255,255,0.04)",
                "borderwidth": 1,
                "bordercolor": "rgba(130,172,191,0.18)",
                "steps": [
                    {"range": [0, 50], "color": "rgba(255,107,107,0.14)"},
                    {"range": [50, 90], "color": "rgba(246,169,59,0.14)"},
                    {"range": [90, 100], "color": "rgba(67,209,127,0.14)"},
                ],
                "threshold": {
                    "line": {"color": "#F3F8FB", "width": 3},
                    "thickness": 0.8,
                    "value": score.score_percent,
                },
            },
        )
    )
    fig.update_layout(height=300, **_LAYOUT_BASE)

    col_gauge, col_meta = st.columns([1.15, 1], gap="large")
    with col_gauge:
        _render_panel_header("Score do perfil ativo", "Prontidão consolidada do cenário selecionado.")
        st.plotly_chart(fig, width="stretch")

    with col_meta:
        _render_panel_header("Leitura do score", "Resumo operacional para tomada de decisão.")
        _render_stat_card(status_label, f"{score.score_percent:.1f}%", f"{score.passed} de {score.total_checks} verificações passaram.")
        _render_stat_card("Issues bloqueantes", score.blocking_issues, "Esses itens impedem o modelo de ser considerado pronto.")
        _render_stat_card("Faixa", _score_band(score), "Classificação visual do nível atual de maturidade.")

    if blocking_issues:
        with st.expander(f"Ver issues bloqueantes ({len(blocking_issues)})", expanded=False):
            for issue in blocking_issues[:12]:
                sev_color = _COLOR_BY_SEVERITY.get(issue.severity, "#94AEBE")
                st.markdown(
                    f"<span style='color:{sev_color};font-size:11px'>&#9632;</span> "
                    f"**{issue.element_class}** `{issue.short_guid}` - {issue.description}",
                    unsafe_allow_html=True,
                )


def _get_blocking_issues(pipeline: QualityPipeline) -> list[Issue]:
    """Retorna issues bloqueantes para o perfil ativo."""
    if pipeline.profile is None or pipeline.report is None:
        return []
    blocking_severities = set(pipeline.profile.blocking_severities)
    return [
        issue
        for issue in pipeline.report.issues
        if issue.issue_type in pipeline.profile.issue_types
        and issue.severity in blocking_severities
        and issue.status not in ("accepted", "edited")
    ]


def _render_readiness_comparison(pipeline: QualityPipeline, issues: list[Issue]) -> None:
    """Renderiza tabela e gráfico comparando os perfis."""
    registry = create_default_registry()
    profiles = registry.list_profiles()
    total_checks = max(1, pipeline.report.total_issues if pipeline.report else 1)

    scores: list[ReadinessScore] = []
    for profile in profiles:
        relevant = [issue for issue in issues if issue.issue_type in profile.issue_types]
        scores.append(ReadinessScore.compute(profile=profile, issues=relevant, total_checks=total_checks))

    rows = [
        {
            "Perfil": score.profile_name,
            "Score": f"{score.score_percent:.1f}%",
            "Status": _LABEL_BY_READINESS[score.status],
            "Issues bloqueantes": score.blocking_issues,
        }
        for score in scores
    ]
    st.dataframe(rows, hide_index=True, width="stretch")

    fig = go.Figure(
        go.Bar(
            x=[score.score_percent for score in scores],
            y=[score.profile_name for score in scores],
            orientation="h",
            marker={
                "color": [_COLOR_BY_READINESS[score.status] for score in scores],
                "line": {"color": "rgba(255,255,255,0.10)", "width": 1},
            },
            text=[f"{score.score_percent:.1f}%" for score in scores],
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>Score: %{x:.1f}%<extra></extra>",
        )
    )
    fig.update_layout(
        title={"text": "Prontidão por perfil", "x": 0.04, "font": {"size": 16}},
        xaxis={"range": [0, 110], "gridcolor": "rgba(130,172,191,0.12)", "zeroline": False, "title": "Score (%)"},
        yaxis={"showgrid": False},
        height=280,
        **_LAYOUT_BASE,
    )
    st.plotly_chart(fig, width="stretch")


def _render_profile_coverage(issues: list[Issue]) -> None:
    """Renderiza tabela de cobertura por perfil."""
    registry = create_default_registry()
    profiles = registry.list_profiles()

    active_types: set[str] = set()
    for profile in profiles:
        active_types.update(profile.issue_types)

    issues_by_type: dict[str, list[Issue]] = {issue_type: [] for issue_type in active_types}
    for issue in issues:
        if issue.issue_type in issues_by_type:
            issues_by_type[issue.issue_type].append(issue)

    rows = []
    for issue_type in sorted(active_types):
        type_issues = issues_by_type.get(issue_type, [])
        row = {"Tipo de issue": _LABEL_BY_TYPE.get(issue_type, issue_type)}
        for profile in profiles:
            if issue_type not in profile.issue_types:
                row[profile.name] = "-"
                continue
            if not type_issues:
                row[profile.name] = "OK"
                continue
            resolved = sum(1 for issue in type_issues if issue.status in ("accepted", "edited"))
            total = len(type_issues)
            row[profile.name] = "OK" if resolved == total else f"{resolved}/{total}"
        rows.append(row)

    st.dataframe(rows, hide_index=True, width="stretch")
    st.markdown(
        "<div class='dashboard-table-caption'>OK = sem impacto aberto no perfil. "
        "Quando houver fração, o valor indica quantas issues daquele tipo já foram resolvidas.</div>",
        unsafe_allow_html=True,
    )


def _render_auditoria_tab(pipeline: QualityPipeline) -> None:
    """Renderiza resumo de auditoria, comparativo antes/depois e benchmark."""
    _render_panel_header("Resumo de auditoria", "Rastro das decisões humanas e das correções aplicadas.")
    _render_audit_summary(pipeline)

    has_corrections = any(issue.status in ("accepted", "edited") for issue, _ in pipeline.issues_suggestions)
    if has_corrections:
        st.divider()
        _render_panel_header("Antes e depois", "Efeito acumulado das correções aplicadas até agora.")
        _render_before_after(pipeline)

    benchmark = getattr(pipeline, "benchmark_results", None)
    if benchmark:
        st.divider()
        _render_panel_header("Benchmark", "Comparativo interno de resolução das sugestões.")
        _render_benchmark(benchmark)


def _render_audit_summary(pipeline: QualityPipeline) -> None:
    """Exibe resumo de auditoria em cards e tabelas."""
    summary = pipeline.audit_logger.get_summary()
    total = summary.get("total_entries", 0)

    if total == 0:
        _render_note("Nenhuma correção foi aplicada ainda. A auditoria será preenchida conforme o engenheiro revisa as issues.")
        return

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        _render_kpi_card("Registros", total, "entradas no log de auditoria", "#63D2FF")
    with col2:
        _render_kpi_card("Aceitas", summary.get("accepted", 0), "correções aplicadas sem edição", "#43D17F")
    with col3:
        _render_kpi_card("Editadas", summary.get("edited", 0), "ajustadas pelo engenheiro", "#F6A93B")
    with col4:
        _render_kpi_card("Rejeitadas", summary.get("rejected", 0), "não escritas no modelo", "#FF6B6B")

    col_action, col_conf, col_src = st.columns(3, gap="large")
    with col_action:
        _render_panel_header("Por ação", "Quais operações de escrita dominaram a revisão.")
        by_action = summary.get("by_action", {})
        if by_action:
            st.dataframe(_dict_to_df(by_action, "Ação", "Total"), hide_index=True, width="stretch")
    with col_conf:
        _render_panel_header("Por confiança", "Distribuição do grau de confiança das sugestões aceitas.")
        by_conf = summary.get("by_confidence", {})
        if by_conf:
            st.dataframe(_dict_to_df(by_conf, "Confiança", "Total"), hide_index=True, width="stretch")
    with col_src:
        _render_panel_header("Por origem", "Origem das decisões aprovadas.")
        by_src = summary.get("by_source", {})
        if by_src:
            st.dataframe(_dict_to_df(by_src, "Origem", "Total"), hide_index=True, width="stretch")


def _dict_to_df(data: dict, key_col: str, val_col: str) -> list[dict]:
    """Converte dict em lista de linhas para st.dataframe."""
    return [{key_col: key, val_col: value} for key, value in sorted(data.items(), key=lambda item: -item[1])]


def _render_before_after(pipeline: QualityPipeline) -> None:
    """Renderiza comparativo antes/depois das correções."""
    report = pipeline.report
    if report is None:
        return

    issues_all = report.issues
    total_before = len(issues_all)
    after_report = _get_after_report(pipeline)

    if after_report is not None:
        issues_after = after_report.issues
        total_after = len(issues_after)
        after_by_type = after_report.issues_by_type
        source_label = "re-análise do modelo corrigido"
    else:
        issues_after = [issue for issue in issues_all if issue.status not in ("accepted", "edited")]
        total_after = len(issues_after)
        after_by_type: dict[str, int] = {}
        for issue in issues_after:
            after_by_type[issue.issue_type] = after_by_type.get(issue.issue_type, 0) + 1
        source_label = "estado atual das correções aplicadas"

    reduction = total_before - total_after
    pct = (reduction / total_before * 100) if total_before > 0 else 0.0

    if pct > 0:
        _render_note(
            f"Antes: {total_before} não conformidades. Agora: {total_after}. "
            f"Redução acumulada de {pct:.0f}% com base em {source_label}."
        )
    elif pct == 0:
        _render_note(f"Nenhuma redução acumulada ainda. A leitura atual usa {source_label}.")
    else:
        _render_note(f"O total atual subiu para {total_after}. A leitura usa {source_label}.")

    all_types = sorted(set(report.issues_by_type) | set(after_by_type))
    if not all_types:
        return

    fig = go.Figure(
        data=[
            go.Bar(
                name="Antes",
                x=[_LABEL_BY_TYPE.get(issue_type, issue_type) for issue_type in all_types],
                y=[report.issues_by_type.get(issue_type, 0) for issue_type in all_types],
                marker_color="#FF6B6B",
                hovertemplate="<b>%{x}</b><br>Antes: %{y}<extra></extra>",
            ),
            go.Bar(
                name="Depois",
                x=[_LABEL_BY_TYPE.get(issue_type, issue_type) for issue_type in all_types],
                y=[after_by_type.get(issue_type, 0) for issue_type in all_types],
                marker_color="#43D17F",
                hovertemplate="<b>%{x}</b><br>Depois: %{y}<extra></extra>",
            ),
        ]
    )
    fig.update_layout(
        title={"text": "Não conformidades por tipo", "x": 0.04, "font": {"size": 16}},
        barmode="group",
        xaxis={"showgrid": False},
        yaxis={"gridcolor": "rgba(130,172,191,0.12)", "title": "Quantidade", "rangemode": "tozero"},
        **_LAYOUT_BASE,
    )
    st.plotly_chart(fig, width="stretch")


def _get_after_report(pipeline: QualityPipeline):
    """Tenta obter o relatório do modelo corrigido usando cache de sessão."""
    cached = st.session_state.get("_after_analysis_report")
    if cached is not None:
        return cached

    corrected_bytes: bytes | None = st.session_state.get("corrected_ifc_bytes")
    if not corrected_bytes:
        return None

    any_applied = any(issue.status in ("accepted", "edited") for issue, _ in pipeline.issues_suggestions)
    if not any_applied:
        return None

    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as tmp:
            tmp.write(corrected_bytes)
            tmp_path = tmp.name

        with st.spinner("Reanalisando modelo corrigido..."):
            after_analyzer = IFCAnalyzer(tmp_path)
            after_report = after_analyzer.analyze()

        st.session_state._after_analysis_report = after_report
        logger.info("Re-análise do modelo corrigido: {} issues restantes.", after_report.total_issues)
        return after_report
    except Exception as exc:
        logger.warning("Não foi possível re-analisar o modelo corrigido: {}", exc)
        return None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _render_benchmark(benchmark: dict) -> None:
    """Renderiza gráficos de benchmark quando disponíveis."""
    col_acc, col_src = st.columns(2, gap="large")

    accuracy_data: dict = benchmark.get("accuracy_by_type", {})
    if accuracy_data:
        with col_acc:
            st.plotly_chart(_bar_accuracy(accuracy_data), width="stretch")

    source_data: dict = benchmark.get("resolved_by_source", {})
    if source_data:
        with col_src:
            st.plotly_chart(_bar_source_comparison(source_data), width="stretch")


def _pie_by_type(issues: list[Issue]) -> go.Figure:
    """Donut de distribuição por tipo."""
    counts: dict[str, int] = {}
    for issue in issues:
        counts[issue.issue_type] = counts.get(issue.issue_type, 0) + 1

    fig = go.Figure(
        go.Pie(
            labels=[_LABEL_BY_TYPE.get(key, key) for key in counts],
            values=list(counts.values()),
            hole=0.58,
            marker={"colors": [_COLOR_BY_TYPE.get(key, "#94AEBE") for key in counts], "line": {"color": "#06131A", "width": 2}},
            textinfo="label+percent",
            textposition="outside",
            sort=False,
            hovertemplate="<b>%{label}</b><br>%{value} issues (%{percent})<extra></extra>",
        )
    )
    fig.update_layout(title={"text": "Backlog por tipo", "x": 0.04, "font": {"size": 16}}, showlegend=False, **_LAYOUT_BASE)
    return fig


def _pie_by_severity(issues: list[Issue]) -> go.Figure:
    """Donut de distribuição por severidade."""
    counts = {severity: 0 for severity in _SEVERITY_ORDER}
    for issue in issues:
        counts[issue.severity] = counts.get(issue.severity, 0) + 1

    non_zero = [severity for severity in _SEVERITY_ORDER if counts[severity] > 0]
    fig = go.Figure(
        go.Pie(
            labels=[_LABEL_BY_SEVERITY[severity] for severity in non_zero],
            values=[counts[severity] for severity in non_zero],
            hole=0.62,
            marker={"colors": [_COLOR_BY_SEVERITY[severity] for severity in non_zero], "line": {"color": "#06131A", "width": 2}},
            textinfo="label+percent",
            hovertemplate="<b>%{label}</b><br>%{value} issues (%{percent})<extra></extra>",
        )
    )
    fig.update_layout(title={"text": "Risco por severidade", "x": 0.04, "font": {"size": 16}}, showlegend=False, **_LAYOUT_BASE)
    return fig


def _bar_by_status(issues: list[Issue]) -> go.Figure:
    """Barras horizontais por status."""
    counts = {status: 0 for status in _STATUS_ORDER}
    for issue in issues:
        counts[issue.status] = counts.get(issue.status, 0) + 1

    fig = go.Figure(
        go.Bar(
            x=[counts[status] for status in _STATUS_ORDER],
            y=[_LABEL_BY_STATUS[status] for status in _STATUS_ORDER],
            orientation="h",
            marker={
                "color": [_COLOR_BY_STATUS[status] for status in _STATUS_ORDER],
                "line": {"color": "rgba(255,255,255,0.08)", "width": 1},
            },
            text=[counts[status] for status in _STATUS_ORDER],
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>%{x} issues<extra></extra>",
        )
    )
    fig.update_layout(
        title={"text": "Distribuição por status", "x": 0.04, "font": {"size": 16}},
        xaxis={"showgrid": True, "gridcolor": "rgba(130,172,191,0.12)", "zeroline": False, "title": "Quantidade"},
        yaxis={"showgrid": False},
        height=340,
        **_LAYOUT_BASE,
    )
    return fig


def _stacked_severity_by_type(issues: list[Issue]) -> go.Figure:
    """Barras empilhadas por tipo e severidade."""
    counts_by_type: dict[str, int] = {}
    counts_by_type_severity: dict[tuple[str, str], int] = {}
    for issue in issues:
        counts_by_type[issue.issue_type] = counts_by_type.get(issue.issue_type, 0) + 1
        key = (issue.issue_type, issue.severity)
        counts_by_type_severity[key] = counts_by_type_severity.get(key, 0) + 1

    issue_types = sorted(counts_by_type, key=counts_by_type.get, reverse=True)
    x_labels = [_LABEL_BY_TYPE.get(issue_type, issue_type) for issue_type in issue_types]

    fig = go.Figure()
    for severity in _SEVERITY_ORDER:
        fig.add_trace(
            go.Bar(
                name=_LABEL_BY_SEVERITY[severity],
                x=x_labels,
                y=[
                    counts_by_type_severity.get((issue_type, severity), 0)
                    for issue_type in issue_types
                ],
                marker_color=_COLOR_BY_SEVERITY[severity],
                hovertemplate="<b>%{x}</b><br>" + _LABEL_BY_SEVERITY[severity] + ": %{y}<extra></extra>",
            )
        )

    fig.update_layout(
        title={"text": "Hotspots por tipo e severidade", "x": 0.04, "font": {"size": 16}},
        barmode="stack",
        xaxis={"showgrid": False},
        yaxis={"gridcolor": "rgba(130,172,191,0.12)", "title": "Issues"},
        height=360,
        **_LAYOUT_BASE,
    )
    return fig


def _bar_accuracy(accuracy_by_type: dict) -> go.Figure:
    """Barras agrupadas de benchmark por tipo."""
    issue_types = list(accuracy_by_type.keys())
    labels = [_LABEL_BY_TYPE.get(issue_type, issue_type) for issue_type in issue_types]

    fig = go.Figure(
        data=[
            go.Bar(
                name="Top-1",
                x=labels,
                y=[accuracy_by_type[issue_type].get("top1", 0) for issue_type in issue_types],
                marker_color="#63D2FF",
                hovertemplate="<b>%{x}</b><br>Top-1: %{y:.1%}<extra></extra>",
            ),
            go.Bar(
                name="Top-3",
                x=labels,
                y=[accuracy_by_type[issue_type].get("top3", 0) for issue_type in issue_types],
                marker_color="#43D17F",
                hovertemplate="<b>%{x}</b><br>Top-3: %{y:.1%}<extra></extra>",
            ),
        ]
    )
    fig.update_layout(
        title={"text": "Acurácia por tipo", "x": 0.04, "font": {"size": 16}},
        barmode="group",
        yaxis={"tickformat": ".0%", "range": [0, 1], "gridcolor": "rgba(130,172,191,0.12)"},
        xaxis={"showgrid": False},
        **_LAYOUT_BASE,
    )
    return fig


def _bar_source_comparison(resolved_by_source: dict) -> go.Figure:
    """Barras por origem de resolução."""
    source_labels = {"llm": "LLM"}
    source_colors = {"llm": "#63D2FF"}
    labels = [source_labels.get(source, source) for source in resolved_by_source]
    values = [resolved_by_source[source] for source in resolved_by_source]

    fig = go.Figure(
        go.Bar(
            x=labels,
            y=values,
            marker={"color": [source_colors.get(source, "#94AEBE") for source in resolved_by_source]},
            text=values,
            textposition="outside",
            hovertemplate="<b>%{x}</b><br>%{y} issues<extra></extra>",
        )
    )
    fig.update_layout(
        title={"text": "Resolução por origem", "x": 0.04, "font": {"size": 16}},
        yaxis={"gridcolor": "rgba(130,172,191,0.12)", "title": "Quantidade"},
        xaxis={"showgrid": False},
        **_LAYOUT_BASE,
    )
    return fig


def _render_panel_header(title: str, subtitle: str) -> None:
    """Renderiza cabeçalho de uma seção."""
    st.markdown(
        f"""
        <div class="dashboard-panel">
            <p class="dashboard-panel-title">{title}</p>
            <p class="dashboard-panel-subtitle">{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_kpi_card(label: str, value, caption: str, accent: str) -> None:
    """Renderiza um card grande de KPI."""
    st.markdown(
        f"""
        <div class="dashboard-kpi" style="box-shadow: inset 0 1px 0 rgba(255,255,255,0.02), 0 24px 60px rgba(0,0,0,0.28);">
            <div class="dashboard-kpi-label" style="color:{accent};">{label}</div>
            <div class="dashboard-kpi-value">{value}</div>
            <div class="dashboard-kpi-delta">{caption}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_stat_card(label: str, value, caption: str) -> None:
    """Renderiza um card compacto de apoio."""
    st.markdown(
        f"""
        <div class="dashboard-stat">
            <div class="dashboard-stat-value">{value}</div>
            <div class="dashboard-stat-label">{label}</div>
            <div class="dashboard-stat-copy">{caption}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_note(text: str) -> None:
    """Renderiza bloco de observação."""
    st.markdown(
        f"<div class='dashboard-note'><strong>Contexto:</strong> {text}</div>",
        unsafe_allow_html=True,
    )


def _compute_issue_counts(issues: list[Issue]) -> dict[str, int]:
    """Consolida contagens de severidade e status."""
    counts = {key: 0 for key in [*_SEVERITY_ORDER, *_STATUS_ORDER]}
    for issue in issues:
        counts[issue.severity] = counts.get(issue.severity, 0) + 1
        counts[issue.status] = counts.get(issue.status, 0) + 1
    return counts


def _format_top_issue_type(issues_by_type: dict[str, int]) -> str:
    """Retorna label do tipo com maior incidência."""
    if not issues_by_type:
        return "Sem issues"
    issue_type = max(issues_by_type, key=issues_by_type.get)
    return _LABEL_BY_TYPE.get(issue_type, issue_type)


def _score_band(score: ReadinessScore) -> str:
    """Faixa legível do readiness score."""
    if score.score_percent >= 90:
        return "Elite"
    if score.score_percent >= 70:
        return "Operável"
    if score.score_percent >= 50:
        return "Instável"
    return "Crítico"


