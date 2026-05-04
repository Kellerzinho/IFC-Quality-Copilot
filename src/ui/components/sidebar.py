"""Componente de sidebar para upload, configuração e exportação do IFC Quality Copilot."""

import json
import os
import tempfile
import base64
from datetime import datetime
from pathlib import Path

import streamlit as st
from loguru import logger

from src.profiles.registry import create_default_registry

_BUILDING_TYPES = [
    "Residencial unifamiliar",
    "Residencial multifamiliar",
    "Comercial",
    "Institucional",
    "Industrial",
]

_BIOCLIMATIC_ZONES = [f"Zona {i}" for i in range(1, 9)]
_GROUNDING_LABELS = {
    "ids_bsdd": "IDS do perfil + bSDD obrigatorio",
}

_PROFILE_NONE = "Nenhum (análise genérica)"
_PROFILE_CUSTOM = "Personalizado (upload IDS)"
_EXPORT_CACHE_KEYS = (
    "corrected_ifc_bytes",
    "audit_csv_bytes",
    "audit_json_bytes",
    "metrics_bytes",
    "bcf_bytes",
)

_registry = create_default_registry()
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_LOGO_IME_PATH = _PROJECT_ROOT / "logoIME.png"


def _logo_ime_base64() -> str:
    """Retorna logo IME em base64 para uso no header da sidebar."""
    return base64.b64encode(_LOGO_IME_PATH.read_bytes()).decode("ascii")


def render_sidebar() -> dict | None:
    """
    Renderiza sidebar com upload e configuração.

    Retorna dict com config se pronto para analisar, None se não.
    """
    with st.sidebar:
        logo_html = ""
        if _LOGO_IME_PATH.exists():
            logo_html = f"<img src='data:image/png;base64,{_logo_ime_base64()}' alt='IME' />"
        st.markdown(
            f"""
            <div class="sidebar-brand">
                {logo_html}
                <div class="sidebar-brand-title">IFC Quality Copilot</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.divider()

        analysis_started = st.session_state.get("analysis_started", False)

        if analysis_started:
            return _render_post_analysis_sidebar()

        return _render_pre_analysis_sidebar()


def _render_pre_analysis_sidebar() -> dict | None:
    """Renderiza formulário de configuração antes da análise."""
    st.session_state["grounding_mode"] = "ids_bsdd"

    ifc_file = st.file_uploader(
        "Upload do modelo IFC",
        type=["ifc"],
        help="Selecione o arquivo IFC do modelo BIM a ser analisado.",
    )

    st.subheader("Perfil de Readiness")

    profiles = _registry.list_profiles()
    profile_options = [_PROFILE_NONE] + [p.name for p in profiles] + [_PROFILE_CUSTOM]

    selected_profile_name = st.selectbox(
        "Perfil de readiness",
        options=profile_options,
        key="profile_select",
    )

    ids_file = None
    profile_id: str | None = None

    if selected_profile_name == _PROFILE_CUSTOM:
        ids_file = st.file_uploader(
            "Arquivo IDS",
            type=["ids", "xml"],
            help="Arquivo IDS com regras customizadas de validação (BuildingSMART).",
            key="ids_uploader_custom",
        )
    elif selected_profile_name != _PROFILE_NONE:
        selected_profile = next((p for p in profiles if p.name == selected_profile_name), None)
        if selected_profile is not None:
            profile_id = selected_profile.id
            st.info(selected_profile.description)

    st.subheader("Contexto da Edificação")

    building_type = st.selectbox(
        "Tipo de edificação",
        options=_BUILDING_TYPES,
        key="building_type_select",
    )

    bioclimatic_zone = st.selectbox(
        "Zona bioclimática",
        options=_BIOCLIMATIC_ZONES,
        key="bioclimatic_zone_select",
        help="Conforme ABNT NBR 15220-3.",
    )

    city = st.text_input("Cidade", key="city_input")
    state = st.text_input("Estado (UF)", key="state_input", max_chars=2)

    st.divider()

    analyze_clicked = st.button(
        "Analisar Modelo",
        type="primary",
        disabled=ifc_file is None,
        width="stretch",
    )

    if ifc_file is None:
        st.caption("Carregue um arquivo IFC para habilitar a análise.")

    if not analyze_clicked or ifc_file is None:
        return None

    return _start_analysis(
        ifc_file,
        ids_file,
        building_type,
        bioclimatic_zone,
        city,
        state,
        profile_id=profile_id,
        is_custom_ids=selected_profile_name == _PROFILE_CUSTOM,
        grounding_mode="ids_bsdd",
    )


def _start_analysis(
    ifc_file,
    ids_file,
    building_type: str,
    bioclimatic_zone: str,
    city: str,
    state: str,
    profile_id: str | None = None,
    is_custom_ids: bool = False,
    grounding_mode: str = "ids_bsdd",
) -> dict | None:
    """Persiste arquivos e contexto no session_state e retorna o dict de configuração."""
    try:
        suffix = Path(ifc_file.name).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(ifc_file.getbuffer())
            ifc_path = tmp.name

        custom_ids_path: str | None = None
        if ids_file is not None and is_custom_ids:
            ids_suffix = Path(ids_file.name).suffix
            with tempfile.NamedTemporaryFile(delete=False, suffix=ids_suffix) as tmp_ids:
                tmp_ids.write(ids_file.getbuffer())
                custom_ids_path = tmp_ids.name

        building_context: dict = {
            "building_type": building_type,
            "bioclimatic_zone": bioclimatic_zone,
            "city": city.strip() if city else "",
            "state": state.strip().upper() if state else "",
            "profile_id": profile_id,
            "custom_ids_path": custom_ids_path,
            "ids_path": custom_ids_path,
            "grounding_mode": grounding_mode,
        }

        st.session_state.ifc_path = ifc_path
        st.session_state.building_context = building_context
        st.session_state.grounding_mode = grounding_mode
        st.session_state.analysis_started = True

        logger.info(
            "Análise iniciada: arquivo={}, tipo={}, zona={}, perfil={}",
            ifc_file.name,
            building_type,
            bioclimatic_zone,
            profile_id or "genérico",
        )

        return building_context

    except Exception as exc:
        logger.error("Erro ao iniciar análise: {}", exc)
        st.error(f"Erro ao processar o arquivo: {exc}")
        return None


def _render_post_analysis_sidebar() -> dict | None:
    """Renderiza progresso, seção de exportação e controles pós-análise."""
    pipeline = st.session_state.get("pipeline")
    issues = []
    if pipeline and pipeline.issues_suggestions:
        issues = [issue for issue, _ in pipeline.issues_suggestions]

    building_context: dict = st.session_state.get("building_context", {})
    profile_id: str | None = building_context.get("profile_id")

    if profile_id is not None:
        _render_readiness_score_card(profile_id, issues)
        st.divider()

    _render_pipeline_mode_card(pipeline, building_context)
    st.divider()

    total = len(issues)
    resolved = sum(1 for i in issues if i.status != "pending")
    progress = resolved / total if total > 0 else 0.0

    st.subheader("Progresso da Revisão")
    st.progress(progress, text=f"{resolved} / {total} issues revisados")

    st.divider()
    st.subheader("Exportar")

    if pipeline is None:
        st.caption("Aguardando análise para habilitar exportação.")
    else:
        model_name = pipeline.report.model_name if pipeline.report else "modelo"
        _render_export_buttons(pipeline, model_name)

    st.divider()

    if st.button("Nova Análise", width="stretch", key="new_analysis"):
        _reset_session()
        st.rerun()

    return None


def _render_readiness_score_card(profile_id: str, issues: list) -> None:
    """Renderiza card de readiness score para o perfil selecionado."""
    profile = _registry.get(profile_id)
    if profile is None:
        return

    from src.models import ReadinessScore

    total_checks = len(issues) or 1  # evita divisão por zero quando análise ainda carrega
    score = ReadinessScore.compute(profile, issues, total_checks)

    st.subheader("Readiness Score")
    st.markdown(
        f"<p style='font-size:2.5rem;font-weight:700;margin:0'>{score.score_percent:.0f}%</p>",
        unsafe_allow_html=True,
    )

    if score.status == "ready":
        st.success("Pronto ✅")
    elif score.status == "partially_ready":
        st.warning("Parcialmente pronto 🟡")
    else:
        st.error("Não pronto 🔴")

    blocking = score.blocking_issues
    label = "issue bloqueante" if blocking == 1 else "issues bloqueantes"
    st.caption(f"{blocking} {label}")


def _render_export_buttons(pipeline, model_name: str) -> None:
    """Renderiza os botões de download na seção Exportar."""

    # --- IFC Corrigido ---
    ifc_bytes = _get_ifc_bytes(pipeline)
    st.download_button(
        label="IFC Corrigido",
        data=ifc_bytes if ifc_bytes else b"",
        file_name=f"{model_name}_corrigido.ifc",
        mime="application/octet-stream",
        disabled=ifc_bytes is None,
        width="stretch",
        key="download_ifc",
    )

    # --- Auditoria CSV ---
    csv_bytes = _get_audit_csv_bytes(pipeline)
    st.download_button(
        label="Auditoria (CSV)",
        data=csv_bytes if csv_bytes else b"",
        file_name=f"{model_name}_auditoria.csv",
        mime="text/csv",
        disabled=csv_bytes is None,
        width="stretch",
        key="download_audit_csv",
    )

    # --- Auditoria JSON ---
    json_bytes = _get_audit_json_bytes(pipeline)
    st.download_button(
        label="Auditoria (JSON)",
        data=json_bytes if json_bytes else b"",
        file_name=f"{model_name}_auditoria.jsonl",
        mime="application/json",
        disabled=json_bytes is None,
        width="stretch",
        key="download_audit_json",
    )

    # --- Issues BCF ---
    bcf_bytes = _get_bcf_bytes(pipeline)
    st.download_button(
        label="Issues (BCF)",
        data=bcf_bytes if bcf_bytes else b"",
        file_name=f"{model_name}_issues.bcf",
        mime="application/octet-stream",
        disabled=bcf_bytes is None,
        width="stretch",
        key="download_bcf",
    )

    # --- Métricas ---
    metrics_bytes = _get_metrics_bytes(pipeline, model_name)
    st.download_button(
        label="Métricas (JSON)",
        data=metrics_bytes,
        file_name=f"{model_name}_metricas.json",
        mime="application/json",
        width="stretch",
        key="download_metrics",
    )


def _render_pipeline_mode_card(pipeline, building_context: dict) -> None:
    """Renderiza resumo do modo de grounding e da pós-validação."""
    grounding_mode = "ids_bsdd"
    st.subheader("Modo do Pipeline")
    st.markdown(
        f"**Base semantica:** {_GROUNDING_LABELS.get(grounding_mode, grounding_mode)}  \n"
    )

    validations = getattr(pipeline, "validation_results", {})
    if validations:
        counts = {"pass": 0, "fail": 0, "skip": 0}
        for result in validations.values():
            counts[result.status] = counts.get(result.status, 0) + 1
        st.caption(
            f"Pós-validação: {counts['pass']} aprovadas, "
            f"{counts['fail']} reprovadas, {counts['skip']} sem gate"
        )


# ---------------------------------------------------------------------------
# Helpers de geração de bytes
# ---------------------------------------------------------------------------


def _get_ifc_bytes(pipeline) -> bytes | None:
    """Serializa o modelo IFC corrigido como bytes via tempfile."""
    # Usa cache do app.py se disponível
    cached = st.session_state.get("corrected_ifc_bytes")
    if cached:
        return cached

    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as tmp:
            tmp_path = tmp.name
        pipeline.writer.salvar(tmp_path)
        with open(tmp_path, "rb") as fh:
            data = fh.read()
        st.session_state.corrected_ifc_bytes = data
        return data
    except Exception as exc:
        logger.warning("Sidebar: erro ao serializar IFC: {}", exc)
        return None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _get_audit_csv_bytes(pipeline) -> bytes | None:
    """Gera CSV de auditoria como bytes."""
    cached = st.session_state.get("audit_csv_bytes")
    if cached:
        return cached

    if not pipeline.audit_logger.entries:
        return None

    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as tmp:
            tmp_path = tmp.name
        pipeline.audit_logger.export_csv(tmp_path)
        with open(tmp_path, "rb") as fh:
            data = fh.read()
        st.session_state.audit_csv_bytes = data
        return data
    except Exception as exc:
        logger.warning("Sidebar: erro ao gerar CSV de auditoria: {}", exc)
        return None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _get_audit_json_bytes(pipeline) -> bytes | None:
    """Gera JSON Lines de auditoria como bytes."""
    cached = st.session_state.get("audit_json_bytes")
    if cached:
        return cached

    if not pipeline.audit_logger.entries:
        return None

    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as tmp:
            tmp_path = tmp.name
        pipeline.audit_logger.export_json(tmp_path)
        with open(tmp_path, "rb") as fh:
            data = fh.read()
        st.session_state.audit_json_bytes = data
        return data
    except Exception as exc:
        logger.warning("Sidebar: erro ao gerar JSON de auditoria: {}", exc)
        return None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _get_metrics_bytes(pipeline, model_name: str) -> bytes:
    """Gera JSON de métricas agregadas do pipeline."""
    cached = st.session_state.get("metrics_bytes")
    if cached:
        return cached

    progress = pipeline.get_progress()
    audit_summary = pipeline.audit_logger.get_summary()

    # Contagens por status
    status_counts: dict[str, int] = {"accepted": 0, "edited": 0, "rejected": 0, "skipped": 0, "pending": 0}
    for issue, _ in pipeline.issues_suggestions:
        if issue.status in status_counts:
            status_counts[issue.status] += 1

    payload = {
        "model_name": model_name,
        "exported_at": datetime.now().isoformat(),
        "progress": {
            **progress,
            **status_counts,
        },
        "audit_summary": audit_summary,
        "building_context": pipeline.building_context,
    }
    data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    st.session_state.metrics_bytes = data
    return data


def _get_bcf_bytes(pipeline) -> bytes | None:
    """Gera pacote BCF como bytes."""
    cached = st.session_state.get("bcf_bytes")
    if cached:
        return cached

    issues = []
    if hasattr(pipeline, "_get_export_issues"):
        issues = pipeline._get_export_issues()
    elif getattr(pipeline, "report", None) is not None:
        issues = list(pipeline.report.issues)

    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".bcf", delete=False) as tmp:
            tmp_path = tmp.name
        pipeline.bcf_exporter.export(issues, Path(tmp_path))
        with open(tmp_path, "rb") as fh:
            data = fh.read()
        st.session_state.bcf_bytes = data
        return data
    except Exception as exc:
        logger.warning("Sidebar: erro ao gerar BCF: {}", exc)
        return None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def invalidate_export_cache() -> None:
    """Remove arquivos exportáveis cacheados da sessão atual."""
    for key in _EXPORT_CACHE_KEYS:
        st.session_state.pop(key, None)


def _reset_session() -> None:
    """Limpa o session_state para permitir uma nova análise."""
    keys_to_clear = [
        "ifc_path",
        "building_context",
        "analysis_started",
        "pipeline",
        "issues_suggestions",
        "current_page",
        "_after_analysis_report",
        "bulk_confirmed",
        "bulk_candidates",
        "_filter_state",
    ]
    for key in keys_to_clear:
        st.session_state.pop(key, None)
    invalidate_export_cache()

    logger.info("Session state limpo. Nova análise iniciada.")
