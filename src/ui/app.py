"""Aplicação Streamlit principal do IFC Quality Copilot."""

import sys
from pathlib import Path
from typing import Any

# Garante que o project root está no sys.path para que `from src.xxx` funcione
# independentemente de como o Streamlit foi invocado.
_PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import streamlit as st
from loguru import logger

from src.models import Issue, SuggestionSet
from src.pipeline import QualityPipeline
from src.profiles.registry import create_default_registry
from src.ui.components.dashboard import render_dashboard
from src.ui.components.filters import render_filters
from src.ui.components.issue_card import render_issue_card
from src.ui.components.progress_bar import render_progress
from src.ui.components.sidebar import invalidate_export_cache, render_sidebar
from src.ui.styles import CUSTOM_CSS

# ---------------------------------------------------------------------------
# Configuração da página — deve ser a primeira chamada Streamlit
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="IFC Quality Copilot",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

_PROFILE_REGISTRY = create_default_registry()
# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    """Função principal da aplicação Streamlit."""
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    config = render_sidebar()

    analysis_started: bool = st.session_state.get("analysis_started", False)
    pipeline: QualityPipeline | None = st.session_state.get("pipeline")

    # --- Inicializar pipeline na primeira execução após upload ---
    if analysis_started and pipeline is None:
        pipeline = _init_pipeline()

    # --- Layout principal ---
    if pipeline is not None:
        _render_main_tabs(pipeline)
    else:
        _render_welcome()


# ---------------------------------------------------------------------------
# Inicialização do pipeline
# ---------------------------------------------------------------------------


def _init_pipeline() -> QualityPipeline | None:
    """
    Cria o pipeline, executa diagnóstico e inicia worker de sugestões em background.

    Armazena resultado em session_state e retorna o pipeline.
    """
    ifc_path: str = st.session_state.get("ifc_path", "")
    building_context: dict = st.session_state.get("building_context", {})
    ids_path: str | None = building_context.get("ids_path")
    profile = _PROFILE_REGISTRY.get(building_context.get("profile_id")) if building_context.get("profile_id") else None

    try:
        pipeline = QualityPipeline(
            ifc_path,
            building_context,
            ids_path,
            profile=profile,
        )
    except Exception as exc:
        st.error(f"Erro ao abrir o arquivo IFC: {exc}")
        logger.error("Erro ao criar QualityPipeline: {}", exc)
        return None

    # Diagnóstico + inicia worker LLM em background
    with st.spinner("Analisando modelo..."):
        try:
            report = pipeline.diagnose_and_start_suggestions()
        except Exception as exc:
            st.error(f"Erro no diagnóstico: {exc}")
            logger.error("Erro em pipeline.diagnose_and_start_suggestions(): {}", exc)
            return None

    if report.total_issues == 0:
        st.success("Nenhuma issue encontrada. Modelo dentro dos padrões!")
        logger.info("Diagnóstico concluído: nenhuma issue encontrada.")
        _store_pipeline(pipeline)
        return pipeline

    _store_pipeline(pipeline)
    logger.info("Pipeline inicializado com {} issues — worker LLM iniciado.", report.total_issues)
    return pipeline


def _store_pipeline(pipeline: QualityPipeline) -> None:
    """Persiste o pipeline e estado inicial no session_state."""
    st.session_state.pipeline = pipeline
    st.session_state.issues_suggestions = pipeline.issues_suggestions
    st.session_state.current_page = 0
    # Limpar estado residual de filtros/lote de sessões anteriores
    for _k in ("bulk_confirmed", "bulk_candidates", "_filter_state", "bulk_select_all", "all_done_shown",
               "_last_progressive_snapshot", "corrected_ifc_bytes", "audit_csv_bytes",
               "audit_json_bytes", "metrics_bytes"):
        st.session_state.pop(_k, None)


# ---------------------------------------------------------------------------
# Layout principal — abas
# ---------------------------------------------------------------------------


def _render_main_tabs(pipeline: QualityPipeline) -> None:
    """Renderiza as abas principais do Copilot."""
    tab_issues, tab_dashboard, tab_guide = st.tabs(["Revisao", "Painel Executivo", "Como Funciona"])

    with tab_issues:
        _render_issues_tab(pipeline)

    with tab_dashboard:
        render_dashboard(pipeline)

    with tab_guide:
        _render_copilot_guide()


# ---------------------------------------------------------------------------
# Aba de Issues
# ---------------------------------------------------------------------------


def _render_issues_tab(pipeline: QualityPipeline) -> None:
    """Renderiza a aba de revisão de issues.

    Modo progressivo: quando pipeline.issue_store está ativo, usa um watcher
    leve para atualizar a revisão somente quando o worker muda algum status.
    Modo legado: comportamento original com lista completa de issues.
    """
    if pipeline.issue_store is not None:
        # Modo progressivo: sugestões chegando em background
        _render_progressive_issues_fragment()
    else:
        # Modo legado: todas as sugestões já foram geradas
        issues_suggestions: list[tuple[Issue, SuggestionSet]] = st.session_state.get(
            "issues_suggestions", pipeline.issues_suggestions
        )
        _handle_bulk_apply(pipeline)
        render_progress(_build_progress_dict(pipeline))
        st.divider()
        all_items = render_filters(issues_suggestions)
        if not all_items:
            st.info("Nenhuma issue disponível para revisão.")
            return
        _render_issue_cards(pipeline, all_items)


_AVAILABLE_FOR_REVIEW = {"ready", "cached", "reused", "review_required"}


def _render_progressive_issues_fragment() -> None:
    """Fragmento de revisão progressiva com atualização manual.

    Estende a UI com status finos (cached / reused / review_required) e
    permite reprocessar individualmente. O worker continua em background, mas
    a lista não rerenderiza em loop para preservar a revisão em uma página só.
    """
    pipeline: QualityPipeline | None = st.session_state.get("pipeline")
    if pipeline is None or pipeline.issue_store is None:
        return

    _handle_bulk_apply(pipeline)
    _handle_requeue_request(pipeline)

    prog = pipeline.get_suggestions_progress()
    is_done = pipeline.issue_store.is_all_done()
    ready_count = (
        prog.get("ready", 0)
        + prog.get("cached", 0)
        + prog.get("reused", 0)
        + prog.get("review_required", 0)
    )
    total = prog.get("total", 0)
    pct = prog.get("percent_complete", 0.0) / 100.0

    # --- Métricas em tempo real ---
    col1, col2, col3, col4, col_refresh = st.columns([1, 1, 1, 1, 1.15])
    with col1:
        st.metric("Disponíveis", f"{ready_count}/{total}")
    with col2:
        st.metric("Cache", prog.get("cached", 0) + prog.get("reused", 0))
    with col3:
        st.metric("Falhas", prog.get("failed", 0) + prog.get("invalid", 0))
    with col4:
        pending_llm = prog.get("queued", 0) + prog.get("processing", 0)
        st.metric("LLM pendente", pending_llm)
    with col_refresh:
        if st.button(
            "Atualizar lista",
            key="refresh_progressive_issues",
            width="stretch",
            help="O processamento continua em background; clique para buscar novas sugestões sem atualizar a página em loop.",
        ):
            st.session_state["_last_progressive_snapshot"] = _progress_snapshot(prog)

    _watch_progressive_updates()

    # --- Barra de progresso animada ---
    if not is_done:
        st.progress(pct, text=f"Gerando sugestões... {prog.get('percent_complete', 0.0):.0f}%")
    else:
        if not st.session_state.get("all_done_shown"):
            st.session_state.all_done_shown = True
        st.success("Todas as sugestões foram geradas!")

    # --- Botão de aceite em lote (habilitado apenas quando concluído) ---
    all_issues_raw = pipeline.get_available_issues()
    high_conf_ids = [
        issue.id
        for issue, sset, status in all_issues_raw
        if status == "ready"
        and sset is not None
        and sset.top_suggestion is not None
        and sset.top_suggestion.confidence == "alta"
        and issue.status == "pending"
    ]
    if high_conf_ids:
        st.button(
            f"Aceitar todas top-1 confiança alta ({len(high_conf_ids)} issues)",
            type="primary",
            disabled=not is_done,
            on_click=_set_bulk_confirm,
            args=(high_conf_ids,),
            key="bulk_accept_progressive",
            help="Disponível após a geração de todas as sugestões." if not is_done else None,
        )

    st.divider()

    # --- Separar issues por status ---
    ready_pairs: list[tuple[Issue, SuggestionSet]] = []
    pending_items: list[tuple[Issue, str]] = []
    failed_items: list[tuple[Issue, str, str | None]] = []
    status_map: dict[str, str] = {}

    for issue, sset, status in all_issues_raw:
        status_map[issue.id] = status
        if status in _AVAILABLE_FOR_REVIEW and sset is not None:
            ready_pairs.append((issue, sset))
        elif status in ("processing", "queued"):
            pending_items.append((issue, status))
        elif status in ("failed", "invalid"):
            error = sset.error if sset is not None else None
            failed_items.append((issue, status, error))

    if ready_pairs:
        all_ready = render_filters(ready_pairs)
        _render_issue_cards(pipeline, all_ready, status_map=status_map)

    if failed_items:
        st.divider()
        st.markdown("**Issues com falha**")
        for issue, status, error in failed_items:
            _render_failed_card(issue, status, error)

    if pending_items:
        if ready_pairs or failed_items:
            st.divider()
        queue_position = 0
        for issue, status in pending_items:
            if status == "processing":
                _render_processing_card(issue)
            else:
                queue_position += 1
                _render_queued_card(issue, queue_position)
    elif not ready_pairs and not failed_items:
        st.info("Nenhuma issue disponível para revisão no momento.")


@st.fragment(run_every="2s")
def _watch_progressive_updates() -> None:
    """Observa o worker e rerenderiza a revisão apenas quando uma issue muda de status."""
    pipeline: QualityPipeline | None = st.session_state.get("pipeline")
    if pipeline is None or pipeline.issue_store is None:
        return

    snapshot = _progress_snapshot(pipeline.get_suggestions_progress())
    previous = st.session_state.get("_last_progressive_snapshot")
    if previous is None:
        st.session_state["_last_progressive_snapshot"] = snapshot
        return
    if snapshot != previous:
        st.session_state["_last_progressive_snapshot"] = snapshot
        st.rerun()


def _progress_snapshot(progress: dict) -> tuple[int, ...]:
    """Assinatura estável do progresso; muda quando uma sugestão fica pronta/falha."""
    keys = (
        "ready",
        "cached",
        "reused",
        "review_required",
        "failed",
        "invalid",
        "processing",
        "queued",
        "total",
    )
    return tuple(int(progress.get(key, 0) or 0) for key in keys)


def _render_processing_card(issue: Issue) -> None:
    """Renderiza card cinza para issue com sugestão LLM sendo gerada."""
    with st.container(border=True):
        col_info, col_spin = st.columns([0.92, 0.08])
        with col_info:
            st.markdown(
                f"**{issue.issue_type}** &nbsp;·&nbsp; "
                f"`{issue.element_name or issue.element_guid}`"
            )
            desc = issue.description
            st.caption(desc[:120] + "..." if len(desc) > 120 else desc)
        with col_spin:
            st.spinner("Gerando sugestão com LLM...")
        st.caption("Gerando sugestão com LLM...")


def _render_queued_card(issue: Issue, position: int) -> None:
    """Renderiza card cinza estático para issue na fila de processamento."""
    with st.container(border=True):
        st.markdown(
            f"**{issue.issue_type}** &nbsp;·&nbsp; "
            f"`{issue.element_name or issue.element_guid}`"
        )
        desc = issue.description
        st.caption(desc[:120] + "..." if len(desc) > 120 else desc)
        st.caption(f"Aguardando... (#{position} na fila)")


def _render_failed_card(issue: Issue, status: str, error: str | None) -> None:
    """Card de issue com falha + botão de reprocessamento."""
    with st.container(border=True):
        col_info, col_btn = st.columns([0.78, 0.22])
        with col_info:
            st.markdown(
                f"**{issue.issue_type}** &nbsp;·&nbsp; `{issue.element_name or issue.element_guid}`"
                f" &nbsp;·&nbsp; status: `{status}`"
            )
            if error:
                st.caption(f"Erro: {error[:160]}")
        with col_btn:
            if st.button("Reprocessar", key=f"requeue_{issue.id}", width="stretch"):
                st.session_state["_requeue_request"] = issue.id


def _handle_requeue_request(pipeline: QualityPipeline) -> None:
    """Recoloca issue na fila quando o engenheiro clicar em Reprocessar."""
    issue_id = st.session_state.pop("_requeue_request", None)
    if issue_id is None or pipeline.issue_store is None:
        return
    pipeline.issue_store.requeue(issue_id)
    if pipeline.worker is None or not pipeline.worker.is_running:
        # Worker pode ter parado quando is_all_done; reinicia
        try:
            pipeline.worker = pipeline.worker  # mantém atributo
            from src.suggestion_engine.worker import SuggestionWorker  # local import
            pipeline.worker = SuggestionWorker(
                store=pipeline.issue_store,
                generator=pipeline.suggestion_gen,
                building_context=pipeline.building_context,
                profile=pipeline.profile,
                ids_context_map=pipeline.ids_context_map,
                bsdd_context_map=pipeline.bsdd_context_map,
                context_builder=pipeline.bsdd_builder,
                reuse_map=pipeline._reuse_map,
                warm_up=True,
            )
            pipeline.worker.start()
        except Exception as exc:
            logger.error("Falha ao reiniciar worker para reprocesso: {}", exc)


def _render_issue_cards(
    pipeline: QualityPipeline,
    filtered: list[tuple[Issue, SuggestionSet]],
    status_map: dict[str, str] | None = None,
) -> None:
    """Renderiza todos os cards filtrados na mesma pagina."""
    for local_idx, (issue, suggestion_set) in enumerate(filtered):
        card_status = (status_map or {}).get(issue.id, "ready")
        result = render_issue_card(
            issue,
            suggestion_set,
            index=local_idx + 1,
            status=card_status,
            audit_entry=pipeline.applied_entries.get(issue.id),
            validation_result=pipeline.get_post_validation_result(issue.id),
        )
        if result is not None:
            _handle_card_decision(pipeline, issue.id, result)
            st.rerun()


# ---------------------------------------------------------------------------
# Aceite em lote
# ---------------------------------------------------------------------------


def _set_bulk_confirm(candidate_ids: list[str]) -> None:
    """Define os candidatos de aceite em lote no session_state (usado como on_click)."""
    st.session_state.bulk_confirmed = True
    st.session_state.bulk_candidates = candidate_ids


def _handle_bulk_apply(pipeline: QualityPipeline) -> None:
    """
    Aplica correções em lote quando o engenheiro confirmou o dialog.

    Lê bulk_confirmed e bulk_candidates do session_state, aplica cada
    correção via pipeline.apply_correction e limpa as chaves ao final.
    """
    if not st.session_state.get("bulk_confirmed"):
        return

    candidate_ids: list[str] = st.session_state.get("bulk_candidates", [])
    applied = 0
    errors = 0

    for issue_id in candidate_ids:
        pair = pipeline.get_issue_by_id(issue_id)
        if pair is None:
            continue
        issue, sset = pair
        if issue.status != "pending":
            continue
        top = sset.top_suggestion
        if top is None:
            continue
        try:
            pipeline.apply_correction(issue_id, top.value, "accepted", user="engineer")
            applied += 1
        except Exception as exc:
            logger.error("Erro no aceite em lote issue={}: {}", issue_id, exc)
            errors += 1

    # Invalida o cache — bytes serão gerados sob demanda ao clicar em Download
    invalidate_export_cache()

    # Limpar flags
    st.session_state.pop("bulk_confirmed", None)
    st.session_state.pop("bulk_candidates", None)
    st.session_state.pop("bulk_select_all", None)

    if applied:
        st.success(f"{applied} correção(ões) aplicada(s) automaticamente.")
    if errors:
        st.warning(f"{errors} correção(ões) falharam — verifique o log.")

    logger.info("Aceite em lote: {} aplicadas, {} erros.", applied, errors)


# ---------------------------------------------------------------------------
# Decisão do card
# ---------------------------------------------------------------------------


def _handle_card_decision(
    pipeline: QualityPipeline,
    issue_id: str,
    result: dict[str, Any],
) -> None:
    """Encaminha a decisão do card para o pipeline e invalida o cache de exportação."""
    decision: str = result["decision"]
    value: Any = result["value"]

    try:
        if decision == "skipped":
            pipeline.skip_issue(issue_id, user="engineer")
        else:
            pipeline.apply_correction(issue_id, value, decision, user="engineer")
        # Invalida o cache — bytes serão gerados sob demanda ao clicar em Download
        invalidate_export_cache()
    except Exception as exc:
        st.error(f"Erro ao aplicar correção: {exc}")
        logger.error("Erro em _handle_card_decision issue={} decision={}: {}", issue_id, decision, exc)


# ---------------------------------------------------------------------------
# Tela de boas-vindas
# ---------------------------------------------------------------------------


def _render_welcome() -> None:
    """Renderiza tela inicial com linguagem institucional e fluxo operacional."""
    st.markdown(
        """
        <section class="welcome-hero">
            <div class="welcome-kicker">Instituto Militar de Engenharia</div>
            <h1 class="welcome-title">IFC Quality Copilot</h1>
            <p class="welcome-subtitle">
                Diagnostico tecnico de modelos BIM/IFC com revisao humana obrigatoria,
                rastreabilidade de auditoria e apoio a decisao de engenharia.
            </p>
        </section>
        """,
        unsafe_allow_html=True,
    )

    st.divider()
    _render_copilot_guide(compact=True)


def _render_copilot_guide(compact: bool = False) -> None:
    """Renderiza guia operacional com fluxo Mermaid e tutorial de uso."""
    if not compact:
        st.markdown(
            """
            <section class="guide-hero">
                <div class="guide-kicker">Guia operacional</div>
                <h2 class="guide-title">Como o IFC Quality Copilot trabalha</h2>
                <p class="guide-copy">
                    O Copilot combina diagnostico IFC, requisitos IDS do perfil,
                    vocabulario bSDD obrigatorio, LLM local e revisao humana.
                    Nenhuma correcao e aplicada sem decisao do engenheiro.
                </p>
            </section>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <section class="guide-hero compact">
                <div class="guide-kicker">Mapa rapido</div>
                <h2 class="guide-title">Fluxo do projeto</h2>
                <p class="guide-copy">
                    Use este roteiro para entender a sequencia da analise antes de carregar o IFC.
                </p>
            </section>
            """,
            unsafe_allow_html=True,
        )

    mermaid_code = """flowchart LR
    A[Upload IFC] --> B[Perfil de readiness]
    B --> C[IDS do perfil]
    A --> D[Diagnostico IFC]
    C --> E[Regras operacionais]
    D --> F[Issues priorizadas]
    E --> F
    F --> G[bSDD obrigatorio]
    G --> H[Prompt ancorado]
    H --> I[LLM local / Ollama]
    I --> J[Sugestoes com proveniencia]
    J --> K{Revisao do engenheiro}
    K -->|Aceitar ou editar| L[Escrita no IFC]
    K -->|Pular| M[Auditoria sem escrita]
    L --> N[Pos-validacao]
    N --> O[Exportar IFC, BCF, CSV, JSON]
    M --> O"""

    mermaid_html = f"""
        <html>
        <head>
            <style>
                body {{
                    margin: 0;
                    background: #0a1720;
                    color: #f4efe3;
                    font-family: Sora, sans-serif;
                    overflow: hidden;
                }}
                .mermaid {{
                    display: flex;
                    justify-content: center;
                    align-items: flex-start;
                    width: 100%;
                    min-width: 1120px;
                    padding: 6px 10px 0 10px;
                    box-sizing: border-box;
                }}
                .mermaid svg {{
                    width: 100% !important;
                    max-width: 1320px !important;
                    height: auto !important;
                }}
            </style>
        </head>
        <body>
        <div class="mermaid">
{mermaid_code}
        </div>
        <script type="module">
            import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
            mermaid.initialize({{
                startOnLoad: true,
                theme: 'base',
                themeVariables: {{
                    background: '#0a1720',
                    primaryColor: '#122632',
                    primaryTextColor: '#f4efe3',
                    primaryBorderColor: '#d7ba6d',
                    lineColor: '#8fa8ba',
                    secondaryColor: '#15313f',
                    tertiaryColor: '#0a1720',
                    fontFamily: 'Sora, sans-serif'
                }}
            }});
        </script>
        </body>
        </html>
        """
    st.iframe(
        mermaid_html,
        height=430,
    )

    tutorial_steps = [
        (
            "1. Carregue o IFC",
            "Use a sidebar para enviar o modelo. A analise so inicia depois do clique em Analisar Modelo.",
        ),
        (
            "2. Escolha o perfil",
            "O perfil define o IDS e o foco de readiness. Se usar IDS proprio, selecione o perfil personalizado.",
        ),
        (
            "3. Informe o contexto",
            "Tipologia, zona bioclimatica, cidade e UF ajudam o Copilot a contextualizar sugestoes.",
        ),
        (
            "4. Revise as issues",
            "Acompanhe as sugestoes chegando em background. Aceite, edite ou pule cada recomendacao.",
        ),
        (
            "5. Exporte artefatos",
            "Baixe IFC corrigido, BCF de issues, auditoria CSV/JSON e metricas para rastreabilidade.",
        ),
    ]

    cols = st.columns(5 if not compact else 3, gap="medium")
    for index, (title, copy) in enumerate(tutorial_steps):
        with cols[index % len(cols)]:
            st.markdown(
                f"""
                <div class="tutorial-card">
                    <div class="tutorial-title">{title}</div>
                    <div class="tutorial-copy">{copy}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_progress_dict(pipeline: QualityPipeline) -> dict:
    """Constrói dict de progresso enriquecido com contagens por status."""
    base = pipeline.get_progress()

    counts: dict[str, int] = {"accepted": 0, "edited": 0, "rejected": 0, "skipped": 0}
    for issue, _ in pipeline.issues_suggestions:
        if issue.status in counts:
            counts[issue.status] += 1

    model_name = pipeline.report.model_name if pipeline.report else ""
    return {**base, **counts, "model_name": model_name}


# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()
