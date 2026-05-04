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

_PAGE_SIZE = 10
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
            grounding_mode="ids_bsdd",
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
               "corrected_ifc_bytes", "audit_csv_bytes", "audit_json_bytes", "metrics_bytes"):
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

    Modo progressivo: quando pipeline.issue_store está ativo, usa fragmento com
    polling automático a cada 2 segundos para exibir progresso em tempo real.
    Modo legado: comportamento original com lista completa de issues.
    """
    if pipeline.issue_store is not None:
        # Modo progressivo: sugestões chegando em background
        # _handle_bulk_apply é chamado dentro do fragment para garantir que
        # rode no mesmo ciclo de rerun que seta bulk_confirmed.
        _render_progressive_issues_fragment()
    else:
        # Modo legado: todas as sugestões já foram geradas
        issues_suggestions: list[tuple[Issue, SuggestionSet]] = st.session_state.get(
            "issues_suggestions", pipeline.issues_suggestions
        )
        _handle_bulk_apply(pipeline)
        render_progress(_build_progress_dict(pipeline))
        st.divider()
        filtered = render_filters(issues_suggestions)
        if not filtered:
            st.info("Nenhuma issue corresponde aos filtros aplicados.")
            return
        _render_paginated_cards(pipeline, filtered)


@st.fragment(run_every="2s")
def _render_progressive_issues_fragment() -> None:
    """Fragmento com auto-refresh a cada 2s para sugestões progressivas.

    Lê pipeline do session_state, exibe métricas em tempo real, cards de
    placeholder para issues em processamento/fila e cards completos para
    issues prontas.
    """
    pipeline: QualityPipeline | None = st.session_state.get("pipeline")
    if pipeline is None or pipeline.issue_store is None:
        return

    # Precisa estar aqui (dentro do fragment) para rodar no mesmo rerun
    # em que on_click seta bulk_confirmed — o fragment rerun não propaga
    # para o contexto pai.
    _handle_bulk_apply(pipeline)

    prog = pipeline.get_suggestions_progress()
    is_done = pipeline.issue_store.is_all_done()
    ready_count = prog.get("ready", 0)
    total = prog.get("total", 0)
    pct = prog.get("percent_complete", 0.0) / 100.0

    # --- Métricas em tempo real ---
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Sugestões prontas", f"{ready_count}/{total}")
    with col2:
        st.metric("Falhas", prog.get("failed", 0))
    with col3:
        pending_llm = prog.get("queued", 0) + prog.get("processing", 0)
        st.metric("LLM pendente", pending_llm)

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

    # --- Separar issues por status e montar mapa id→status ---
    ready_pairs: list[tuple[Issue, SuggestionSet]] = []
    pending_items: list[tuple[Issue, str]] = []  # (issue, status)
    status_map: dict[str, str] = {}

    for issue, sset, status in all_issues_raw:
        status_map[issue.id] = status
        if status == "ready" and sset is not None:
            ready_pairs.append((issue, sset))
        elif status in ("processing", "queued"):
            pending_items.append((issue, status))

    if ready_pairs:
        filtered = render_filters(ready_pairs)
        if filtered:
            _render_paginated_cards(pipeline, filtered, status_map=status_map)
        else:
            st.info("Nenhuma issue corresponde aos filtros aplicados.")

    if pending_items:
        if ready_pairs:
            st.divider()
        queue_position = 0
        for issue, status in pending_items:
            if status == "processing":
                _render_processing_card(issue)
            else:
                queue_position += 1
                _render_queued_card(issue, queue_position)
    elif not ready_pairs:
        st.info("Nenhuma issue disponível.")


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


def _render_paginated_cards(
    pipeline: QualityPipeline,
    filtered: list[tuple[Issue, SuggestionSet]],
    status_map: dict[str, str] | None = None,
) -> None:
    """Renderiza cards paginados com controles de navegação."""
    total_pages = max(1, (len(filtered) + _PAGE_SIZE - 1) // _PAGE_SIZE)
    current_page = min(st.session_state.get("current_page", 0), total_pages - 1)
    st.session_state.current_page = current_page

    page_items = filtered[current_page * _PAGE_SIZE : (current_page + 1) * _PAGE_SIZE]
    global_start = current_page * _PAGE_SIZE

    for local_idx, (issue, suggestion_set) in enumerate(page_items):
        card_status = (status_map or {}).get(issue.id, "ready")
        result = render_issue_card(
            issue,
            suggestion_set,
            index=global_start + local_idx + 1,
            status=card_status,
            audit_entry=pipeline.applied_entries.get(issue.id),
            validation_result=pipeline.get_post_validation_result(issue.id),
        )
        if result is not None:
            _handle_card_decision(pipeline, issue.id, result)
            st.rerun()

    _render_pagination(current_page, total_pages, len(filtered))


def _render_pagination(current_page: int, total_pages: int, total_items: int) -> None:
    """Renderiza controles de paginação."""
    st.divider()
    col_prev, col_info, col_next = st.columns([1, 3, 1])

    with col_prev:
        if st.button(
            "Anterior",
            disabled=current_page == 0,
            key="page_prev",
            width="stretch",
        ):
            st.session_state.current_page -= 1
            st.rerun()

    with col_info:
        start = current_page * _PAGE_SIZE + 1
        end = min(start + _PAGE_SIZE - 1, total_items)
        st.markdown(
            f"<div style='text-align:center; padding-top:0.4rem; color:#94A3B8; font-size:0.85rem;'>"
            f"Página {current_page + 1} de {total_pages} &nbsp;·&nbsp; "
            f"Issues {start}–{end} de {total_items}"
            f"</div>",
            unsafe_allow_html=True,
        )

    with col_next:
        if st.button(
            "Próxima",
            disabled=current_page >= total_pages - 1,
            key="page_next",
            width="stretch",
        ):
            st.session_state.current_page += 1
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
