"""Tools MCP integradas ao QualityPipeline completo."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import mcp.types as types

from src.models import Issue, SuggestionSet
from src.pipeline import QualityPipeline
from src.profiles.registry import create_default_registry


def _json_response(data: dict) -> list[types.TextContent]:
    from src.mcp_server.server import _json_response as _server_json_response

    return _server_json_response(data)


def _approval_error() -> list[types.TextContent]:
    return _json_response({"sucesso": False, "erro": "Operacao requer aprovacao explicita do usuario."})


def _pipeline_error() -> list[types.TextContent]:
    return _json_response({
        "sucesso": False,
        "erro": "Nenhum pipeline ativo. Use 'iniciar_pipeline' primeiro.",
    })


def _get_pipeline(session: dict) -> QualityPipeline | None:
    pipeline = session.get("pipeline")
    return pipeline if isinstance(pipeline, QualityPipeline) else None


def _all_issue_items(pipeline: QualityPipeline) -> list[dict[str, Any]]:
    if pipeline.issue_store is not None:
        return pipeline.issue_store.get_all_with_status()
    if pipeline.issues_suggestions:
        return [
            {"issue": issue, "suggestion": suggestion_set, "status": issue.status, "reused_from": None}
            for issue, suggestion_set in pipeline.issues_suggestions
        ]
    if pipeline.report is not None:
        return [
            {"issue": issue, "suggestion": None, "status": issue.status, "reused_from": None}
            for issue in pipeline.report.issues
        ]
    return []


def _find_issue_item(pipeline: QualityPipeline, issue_id: str) -> dict[str, Any] | None:
    for item in _all_issue_items(pipeline):
        if item["issue"].id == issue_id:
            return item
    return None


def _serialize_issue(issue: Issue, *, include_context: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "issue_id": issue.id,
        "guid": issue.element_guid,
        "classe": issue.element_class,
        "nome": issue.element_name,
        "tipo": issue.issue_type,
        "rotulo": issue.type_label,
        "severidade": issue.severity,
        "descricao": issue.description,
        "status_revisao": issue.status,
        "valor_resolucao": issue.resolution_value,
    }
    if include_context:
        payload["contexto"] = issue.context
    return payload


def _serialize_suggestion_set(suggestion_set: SuggestionSet | None) -> dict[str, Any] | None:
    if suggestion_set is None:
        return None
    return {
        "issue_id": suggestion_set.issue_id,
        "erro": suggestion_set.error,
        "prompt_hash": suggestion_set.prompt_hash,
        "allow_custom": suggestion_set.allow_custom,
        "metricas": suggestion_set.metrics.model_dump() if suggestion_set.metrics else None,
        "sugestoes": [
            {
                "indice": index,
                "label": suggestion.label,
                "valor": suggestion.value,
                "justificativa": suggestion.justification,
                "confianca": suggestion.confidence,
                "referencia_normativa": suggestion.normative_ref,
                "review_required": suggestion.review_required,
                "canonical_term": suggestion.canonical_term,
                "semantic_hint": suggestion.semantic_hint,
                "semantic_status": suggestion.semantic_status,
                "bsdd_uri": suggestion.bsdd_uri,
                "ids_requirement_id": suggestion.ids_requirement_id,
            }
            for index, suggestion in enumerate(
                sorted(suggestion_set.suggestions, key=lambda s: s.confidence_order)
            )
        ],
    }


def _build_pipeline(
    filepath: str,
    building_context: dict[str, Any],
    profile_id: str | None,
    ids_path: str | None,
) -> QualityPipeline:
    registry = create_default_registry()
    profile = registry.get(profile_id) if profile_id else None
    return QualityPipeline(
        filepath,
        building_context,
        ids_path=ids_path,
        profile=profile,
    )


async def handle_iniciar_pipeline(session: dict, arguments: dict) -> list[types.TextContent]:
    """Carrega IFC, executa diagnostico e inicia geracao de sugestoes em background."""
    filepath = str(arguments.get("filepath") or "").strip()
    if not filepath:
        return _json_response({"sucesso": False, "erro": "Parametro 'filepath' e obrigatorio."})
    path = Path(filepath)
    if not path.exists() or path.suffix.lower() != ".ifc":
        return _json_response({"sucesso": False, "erro": f"Arquivo IFC invalido: {filepath}"})

    old_pipeline = _get_pipeline(session)
    if old_pipeline is not None:
        old_pipeline.close()

    profile_id = arguments.get("profile_id")
    ids_path = arguments.get("ids_path")
    building_context = dict(arguments.get("building_context") or {})
    if profile_id:
        building_context.setdefault("profile_id", profile_id)
    if ids_path:
        building_context.setdefault("ids_path", ids_path)

    try:
        pipeline = _build_pipeline(filepath, building_context, profile_id, ids_path)
        report = pipeline.diagnose_and_start_suggestions()
    except Exception as exc:
        return _json_response({"sucesso": False, "erro": str(exc)})

    session["pipeline"] = pipeline
    session["analyzer"] = pipeline.analyzer
    session["writer"] = pipeline.writer
    session["audit_logger"] = pipeline.audit_logger
    session["profile_id"] = profile_id

    return _json_response({
        "sucesso": True,
        "modelo": report.model_name,
        "total_issues": report.total_issues,
        "issues_por_tipo": report.issues_by_type,
        "issues_por_severidade": report.issues_by_severity,
        "profile_id": profile_id,
        "sugestoes_em_background": True,
    })


async def handle_progresso_sugestoes(session: dict, arguments: dict) -> list[types.TextContent]:
    pipeline = _get_pipeline(session)
    if pipeline is None:
        return _pipeline_error()
    return _json_response({
        "sucesso": True,
        "progresso": pipeline.get_suggestions_progress(),
        "worker_ativo": bool(pipeline.worker and pipeline.worker.is_running),
    })


async def handle_listar_issues(session: dict, arguments: dict) -> list[types.TextContent]:
    pipeline = _get_pipeline(session)
    if pipeline is None:
        return _pipeline_error()

    issue_type = arguments.get("issue_type")
    severity = arguments.get("severity")
    review_status = arguments.get("review_status")
    suggestion_status = arguments.get("suggestion_status")
    include_context = bool(arguments.get("include_context", False))
    limit = int(arguments.get("limit", 100))
    offset = int(arguments.get("offset", 0))

    items = _all_issue_items(pipeline)
    filtered: list[dict[str, Any]] = []
    for item in items:
        issue: Issue = item["issue"]
        if issue_type and issue.issue_type != issue_type:
            continue
        if severity and issue.severity != severity:
            continue
        if review_status and issue.status != review_status:
            continue
        if suggestion_status and item.get("status") != suggestion_status:
            continue
        filtered.append(item)

    page = filtered[offset: offset + limit]
    return _json_response({
        "sucesso": True,
        "total": len(filtered),
        "offset": offset,
        "limit": limit,
        "issues": [
            {
                **_serialize_issue(item["issue"], include_context=include_context),
                "status_sugestao": item.get("status"),
                "reusada_de": item.get("reused_from"),
            }
            for item in page
        ],
    })


async def handle_obter_contexto_issue(session: dict, arguments: dict) -> list[types.TextContent]:
    pipeline = _get_pipeline(session)
    if pipeline is None:
        return _pipeline_error()

    issue_id = arguments.get("issue_id")
    item = _find_issue_item(pipeline, issue_id)
    if item is None:
        return _json_response({"sucesso": False, "erro": f"Issue nao encontrada: {issue_id}"})

    issue: Issue = item["issue"]
    return _json_response({
        "sucesso": True,
        "issue": _serialize_issue(issue, include_context=True),
        "status_sugestao": item.get("status"),
        "sugestoes": _serialize_suggestion_set(item.get("suggestion")),
        "ids_context": (
            pipeline.ids_context_map[issue.id].model_dump()
            if issue.id in pipeline.ids_context_map else None
        ),
        "bsdd_context": (
            pipeline.bsdd_context_map[issue.id].model_dump()
            if issue.id in pipeline.bsdd_context_map else None
        ),
    })


async def handle_listar_sugestoes(session: dict, arguments: dict) -> list[types.TextContent]:
    pipeline = _get_pipeline(session)
    if pipeline is None:
        return _pipeline_error()

    issue_id = arguments.get("issue_id")
    include_pending = bool(arguments.get("include_pending", False))
    items = _all_issue_items(pipeline)
    if issue_id:
        items = [item for item in items if item["issue"].id == issue_id]

    payload = []
    for item in items:
        suggestion_set = item.get("suggestion")
        if suggestion_set is None and not include_pending:
            continue
        payload.append({
            "issue": _serialize_issue(item["issue"], include_context=False),
            "status_sugestao": item.get("status"),
            "sugestoes": _serialize_suggestion_set(suggestion_set),
        })

    return _json_response({"sucesso": True, "total": len(payload), "items": payload})


async def handle_explicar_sugestao(session: dict, arguments: dict) -> list[types.TextContent]:
    pipeline = _get_pipeline(session)
    if pipeline is None:
        return _pipeline_error()

    issue_id = arguments.get("issue_id")
    suggestion_index = int(arguments.get("suggestion_index", 0))
    item = _find_issue_item(pipeline, issue_id)
    if item is None:
        return _json_response({"sucesso": False, "erro": f"Issue nao encontrada: {issue_id}"})
    suggestion_set: SuggestionSet | None = item.get("suggestion")
    if suggestion_set is None or not suggestion_set.suggestions:
        return _json_response({"sucesso": False, "erro": "Sugestoes ainda nao disponiveis para esta issue."})

    ordered = sorted(suggestion_set.suggestions, key=lambda s: s.confidence_order)
    if suggestion_index < 0 or suggestion_index >= len(ordered):
        return _json_response({"sucesso": False, "erro": "suggestion_index fora do intervalo."})

    issue: Issue = item["issue"]
    suggestion = ordered[suggestion_index]
    evidence_keys = [
        "check_property",
        "pset_name",
        "material_name",
        "thickness_m",
        "is_external",
        "area_m2",
        "height_m",
        "perimeter_m",
        "floor",
        "contained_elements",
        "adjacent_spaces",
        "materials",
        "total_thickness",
    ]
    evidencias = {key: issue.context.get(key) for key in evidence_keys if key in issue.context}
    return _json_response({
        "sucesso": True,
        "issue": _serialize_issue(issue, include_context=False),
        "sugestao": {
            "indice": suggestion_index,
            "label": suggestion.label,
            "valor": suggestion.value,
            "confianca": suggestion.confidence,
            "justificativa": suggestion.justification,
            "review_required": suggestion.review_required,
        },
        "evidencias_ifc": evidencias,
        "ids_context": (
            pipeline.ids_context_map[issue.id].model_dump()
            if issue.id in pipeline.ids_context_map else None
        ),
        "bsdd_context": (
            pipeline.bsdd_context_map[issue.id].model_dump()
            if issue.id in pipeline.bsdd_context_map else None
        ),
        "metricas": suggestion_set.metrics.model_dump() if suggestion_set.metrics else None,
    })


async def handle_aplicar_sugestao(session: dict, arguments: dict) -> list[types.TextContent]:
    pipeline = _get_pipeline(session)
    if pipeline is None:
        return _pipeline_error()
    if not arguments.get("aprovado_pelo_usuario"):
        return _approval_error()

    issue_id = arguments.get("issue_id")
    decision = arguments.get("decision") or "accepted"
    suggestion_index = int(arguments.get("suggestion_index", 0))
    custom_value = arguments.get("valor_customizado")

    pair = pipeline.get_issue_by_id(issue_id)
    if pair is None:
        return _json_response({"sucesso": False, "erro": f"Issue nao encontrada ou sem sugestao: {issue_id}"})
    issue, suggestion_set = pair

    try:
        if decision == "skipped":
            pipeline.skip_issue(issue_id, user=arguments.get("usuario", "mcp"))
            return _json_response({"sucesso": True, "issue_id": issue_id, "decision": "skipped"})

        if custom_value is not None:
            value = custom_value
            decision = "edited"
        else:
            ordered = sorted(suggestion_set.suggestions, key=lambda s: s.confidence_order)
            if suggestion_index < 0 or suggestion_index >= len(ordered):
                return _json_response({"sucesso": False, "erro": "suggestion_index fora do intervalo."})
            value = ordered[suggestion_index].value

        entry = pipeline.apply_correction(
            issue_id,
            value,
            decision,
            user=arguments.get("usuario", "mcp"),
        )
    except Exception as exc:
        return _json_response({"sucesso": False, "erro": str(exc)})

    validation = pipeline.get_post_validation_result(issue_id)
    return _json_response({
        "sucesso": True,
        "issue_id": issue_id,
        "guid": issue.element_guid,
        "decision": decision,
        "valor_aplicado": issue.resolution_value,
        "auditoria": entry.model_dump(mode="json"),
        "post_validacao": validation.model_dump() if validation else None,
    })


async def handle_pos_validar_issue(session: dict, arguments: dict) -> list[types.TextContent]:
    pipeline = _get_pipeline(session)
    if pipeline is None:
        return _pipeline_error()

    guid = arguments.get("guid")
    issue_id = arguments.get("issue_id")
    if not guid and issue_id:
        item = _find_issue_item(pipeline, issue_id)
        if item is not None:
            guid = item["issue"].element_guid
    if not guid:
        return _json_response({"sucesso": False, "erro": "Informe guid ou issue_id."})

    result = pipeline.post_validator.validate_element(guid)
    return _json_response({"sucesso": True, "resultado": result.model_dump()})


async def handle_exportar_artefatos(session: dict, arguments: dict) -> list[types.TextContent]:
    pipeline = _get_pipeline(session)
    if pipeline is None:
        return _pipeline_error()

    output_dir = arguments.get("output_dir")
    if not output_dir:
        output_dir = tempfile.mkdtemp(prefix="ifc_copilot_mcp_")

    try:
        result = pipeline.export(str(output_dir))
    except Exception as exc:
        return _json_response({"sucesso": False, "erro": str(exc)})

    return _json_response({"sucesso": True, "arquivos": result})


async def handle_fechar_pipeline(session: dict, arguments: dict) -> list[types.TextContent]:
    pipeline = _get_pipeline(session)
    if pipeline is not None:
        pipeline.close()
    session["pipeline"] = None
    session["analyzer"] = None
    session["writer"] = None
    return _json_response({"sucesso": True})


PIPELINE_TOOLS = [
    types.Tool(
        name="iniciar_pipeline",
        description=(
            "Carrega um IFC, executa diagnostico completo com o QualityPipeline e inicia a geracao "
            "de sugestoes LLM em background usando IDS/bSDD conforme o perfil informado."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "Caminho completo do arquivo .ifc."},
                "profile_id": {
                    "type": "string",
                    "description": "Perfil opcional: budget_readiness, energy_readiness, fm_readiness, etc.",
                },
                "ids_path": {"type": "string", "description": "IDS customizado opcional."},
                "building_context": {"type": "object", "description": "Contexto livre da edificacao."},
            },
            "required": ["filepath"],
        },
    ),
    types.Tool(
        name="progresso_sugestoes",
        description="Retorna progresso da fila de sugestoes LLM do pipeline ativo.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    types.Tool(
        name="listar_issues",
        description="Lista issues do pipeline ativo com filtros por tipo, severidade, status e paginacao.",
        inputSchema={
            "type": "object",
            "properties": {
                "issue_type": {"type": "string"},
                "severity": {"type": "string", "enum": ["high", "medium", "low"]},
                "review_status": {"type": "string"},
                "suggestion_status": {"type": "string"},
                "include_context": {"type": "boolean", "default": False},
                "limit": {"type": "integer", "default": 100},
                "offset": {"type": "integer", "default": 0},
            },
            "required": [],
        },
    ),
    types.Tool(
        name="obter_contexto_issue",
        description="Retorna contexto IFC, IDS, bSDD e sugestoes de uma issue especifica.",
        inputSchema={
            "type": "object",
            "properties": {"issue_id": {"type": "string"}},
            "required": ["issue_id"],
        },
    ),
    types.Tool(
        name="listar_sugestoes",
        description="Lista sugestoes LLM geradas pelo pipeline, ordenadas por confianca.",
        inputSchema={
            "type": "object",
            "properties": {
                "issue_id": {"type": "string"},
                "include_pending": {"type": "boolean", "default": False},
            },
            "required": [],
        },
    ),
    types.Tool(
        name="explicar_sugestao",
        description="Explica uma sugestao usando evidencias IFC, IDS, bSDD e metricas do pipeline.",
        inputSchema={
            "type": "object",
            "properties": {
                "issue_id": {"type": "string"},
                "suggestion_index": {"type": "integer", "default": 0},
            },
            "required": ["issue_id"],
        },
    ),
    types.Tool(
        name="aplicar_sugestao",
        description=(
            "Aplica uma sugestao do pipeline ou um valor editado. Requer aprovado_pelo_usuario=true "
            "e executa escrita, auditoria e pos-validacao."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "issue_id": {"type": "string"},
                "suggestion_index": {"type": "integer", "default": 0},
                "valor_customizado": {},
                "decision": {"type": "string", "enum": ["accepted", "edited", "skipped"]},
                "usuario": {"type": "string", "default": "mcp"},
                "aprovado_pelo_usuario": {"type": "boolean"},
            },
            "required": ["issue_id", "aprovado_pelo_usuario"],
        },
    ),
    types.Tool(
        name="pos_validar_issue",
        description="Executa pos-validacao de um elemento por issue_id ou guid.",
        inputSchema={
            "type": "object",
            "properties": {"issue_id": {"type": "string"}, "guid": {"type": "string"}},
            "required": [],
        },
    ),
    types.Tool(
        name="exportar_artefatos",
        description="Exporta IFC corrigido, auditoria, BCF e metricas para um diretorio.",
        inputSchema={
            "type": "object",
            "properties": {"output_dir": {"type": "string"}},
            "required": [],
        },
    ),
    types.Tool(
        name="fechar_pipeline",
        description="Fecha recursos do pipeline ativo e limpa a sessao MCP.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
]
