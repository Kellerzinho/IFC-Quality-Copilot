"""MCP server principal do IFC Quality Copilot."""

import asyncio
import json
from pathlib import Path
from typing import Any

import mcp.server as mcp_server
import mcp.types as types
from loguru import logger
from mcp.server.stdio import stdio_server

from src.audit.logger import AuditLogger
from src.ifc_analyzer import IFCAnalyzer
from src.mcp_server.registry import ToolRegistry
from src.mcp_server.tools_read import (
    DIAGNOSTIC_TOOLS,
    handle_diagnosticar_espacos,
    handle_diagnosticar_psets,
    handle_diagnosticar_relacoes,
    handle_diagnosticar_sistemas,
    handle_listar_tools_disponiveis,
    handle_verificar_readiness,
)
from src.mcp_server.tools_pipeline import (
    PIPELINE_TOOLS,
    handle_aplicar_sugestao,
    handle_explicar_sugestao,
    handle_exportar_artefatos,
    handle_fechar_pipeline,
    handle_iniciar_pipeline,
    handle_listar_issues,
    handle_listar_sugestoes,
    handle_obter_contexto_issue,
    handle_pos_validar_issue,
    handle_progresso_sugestoes,
)
from src.mcp_server.tools_write import (
    WRITE_TOOLS,
    handle_associar_zona_termica,
    handle_classificar_sistema,
    handle_criar_relacao_fills,
    handle_mapear_classificacao,
    handle_preencher_base_quantities,
    handle_preencher_pset,
    handle_registrar_log,
    handle_renomear_espaco,
)
from src.writer.ifc_writer import IFCWriter

server = mcp_server.Server("ifc-quality-copilot")

_session: dict[str, Any] = {
    "analyzer": None,
    "writer": None,
    "audit_logger": AuditLogger(),
    "pipeline": None,
    "profile_id": None,
    "tool_registry": None,
}

_CLASSES_PRINCIPAIS = [
    "IfcWall",
    "IfcSpace",
    "IfcDoor",
    "IfcWindow",
    "IfcSlab",
    "IfcColumn",
    "IfcBeam",
    "IfcStair",
    "IfcRoof",
    "IfcCovering",
    "IfcFurnishingElement",
    "IfcFlowTerminal",
]


def _json_response(data: dict) -> list[types.TextContent]:
    """Serializa dict como TextContent JSON."""
    return [types.TextContent(type="text", text=json.dumps(data, ensure_ascii=False, indent=2))]


# ---------------------------------------------------------------------------
# Handlers internos (carregar_modelo / resumo_modelo)
# ---------------------------------------------------------------------------

async def _carregar_modelo(arguments: dict) -> list[types.TextContent]:
    """Implementação da tool carregar_modelo."""
    filepath: str = arguments.get("filepath", "")
    path = Path(filepath)

    if not path.exists():
        logger.warning("Arquivo não encontrado: {}", filepath)
        return _json_response({"sucesso": False, "erro": f"Arquivo não encontrado: '{filepath}'"})

    if path.suffix.lower() != ".ifc":
        logger.warning("Extensão inválida: {}", path.suffix)
        return _json_response({
            "sucesso": False,
            "erro": f"O arquivo deve ter extensão .ifc, recebido: '{path.suffix}'",
        })

    try:
        analyzer = IFCAnalyzer(str(path))
    except Exception as exc:
        logger.error("Falha ao abrir IFC '{}': {}", filepath, exc)
        return _json_response({
            "sucesso": False,
            "erro": f"Não foi possível abrir o arquivo IFC: {exc}",
        })

    _session["analyzer"] = analyzer
    _session["writer"] = IFCWriter(analyzer.ifc_file)
    total = len(analyzer.ifc_file.by_type("IfcProduct"))
    schema = analyzer.ifc_file.schema

    logger.info("Modelo '{}' carregado via MCP ({} elementos, {})", analyzer.model_name, total, schema)
    return _json_response({
        "sucesso": True,
        "modelo": analyzer.model_name,
        "total_elementos": total,
        "schema": schema,
    })


async def _resumo_modelo() -> list[types.TextContent]:
    """Implementação da tool resumo_modelo."""
    analyzer: IFCAnalyzer | None = _session.get("analyzer")

    if analyzer is None:
        return _json_response({
            "sucesso": False,
            "erro": "Nenhum modelo carregado. Use 'carregar_modelo' primeiro.",
        })

    summary = analyzer.get_model_summary()
    ifc_file = analyzer.ifc_file

    por_classe: dict[str, int] = {
        cls: len(ifc_file.by_type(cls)) for cls in _CLASSES_PRINCIPAIS
    }

    psets_encontrados: list[str] = sorted({
        ps.Name
        for ps in ifc_file.by_type("IfcPropertySet")
        if ps.Name
    })

    classificacoes: list[str] = []
    for rel in ifc_file.by_type("IfcRelAssociatesClassification"):
        ref = rel.RelatingClassification
        name: str | None = getattr(ref, "Name", None) or getattr(ref, "ItemReference", None)
        if name and name not in classificacoes:
            classificacoes.append(name)
    classificacoes.sort()

    return _json_response({
        "nome": summary["model_name"],
        "schema": summary["schema"],
        "total_elementos": summary["total_elements"],
        "por_classe": por_classe,
        "psets_encontrados": psets_encontrados,
        "classificacoes_encontradas": classificacoes,
    })


# ---------------------------------------------------------------------------
# Wrappers de session para handlers que não recebem arguments
# ---------------------------------------------------------------------------

async def _wrap_carregar_modelo(session: dict, arguments: dict) -> list[types.TextContent]:
    """Wrapper para compatibilidade com a assinatura (session, arguments) do registry."""
    return await _carregar_modelo(arguments)


async def _wrap_resumo_modelo(session: dict, arguments: dict) -> list[types.TextContent]:
    """Wrapper para compatibilidade com a assinatura (session, arguments) do registry."""
    return await _resumo_modelo()


async def _wrap_diagnosticar_espacos(session: dict, arguments: dict) -> list[types.TextContent]:
    """Wrapper que ignora arguments (diagnosticar_espacos não tem parâmetros)."""
    return await handle_diagnosticar_espacos(session)


async def _wrap_diagnosticar_relacoes(session: dict, arguments: dict) -> list[types.TextContent]:
    """Wrapper que ignora arguments (diagnosticar_relacoes não tem parâmetros)."""
    return await handle_diagnosticar_relacoes(session)


async def _wrap_diagnosticar_sistemas(session: dict, arguments: dict) -> list[types.TextContent]:
    """Wrapper que ignora arguments (diagnosticar_sistemas não tem parâmetros)."""
    return await handle_diagnosticar_sistemas(session)


# ---------------------------------------------------------------------------
# ToolRegistry — construção e registro global
# ---------------------------------------------------------------------------

def _build_registry() -> ToolRegistry:
    """Constrói e retorna o ToolRegistry com todas as tools e seus perfis."""
    # Indexa DIAGNOSTIC_TOOLS e WRITE_TOOLS por nome para extrair description/schema
    _tool_meta: dict[str, types.Tool] = {
        t.name: t for t in [*DIAGNOSTIC_TOOLS, *WRITE_TOOLS, *PIPELINE_TOOLS]
    }

    registry = ToolRegistry()

    # --- Ferramentas gerais (disponíveis em todos os perfis) ---
    registry.register(
        name="carregar_modelo",
        handler=_wrap_carregar_modelo,
        schema={
            "type": "object",
            "properties": {"filepath": {"type": "string", "description": "Caminho completo para o arquivo .ifc."}},
            "required": ["filepath"],
        },
        description=(
            "Abre um arquivo IFC do disco e o carrega na sessão atual. "
            "Deve ser a primeira ferramenta chamada antes de qualquer outra operação."
        ),
        profiles=None,
        category="general",
    )
    registry.register(
        name="resumo_modelo",
        handler=_wrap_resumo_modelo,
        schema={"type": "object", "properties": {}, "required": []},
        description=(
            "Retorna um resumo estruturado do modelo IFC atualmente carregado. "
            "Inclui schema IFC, total de elementos, contagem por classe e PropertySets presentes."
        ),
        profiles=None,
        category="general",
    )
    registry.register(
        name="listar_tools_disponiveis",
        handler=handle_listar_tools_disponiveis,
        schema=_tool_meta["listar_tools_disponiveis"].input_schema,
        description=_tool_meta["listar_tools_disponiveis"].description,
        profiles=None,
        category="general",
    )

    # --- Ferramentas de diagnóstico ---
    _diag_handlers: dict[str, Any] = {
        "diagnosticar_espacos": _wrap_diagnosticar_espacos,
        "diagnosticar_psets": handle_diagnosticar_psets,
        "diagnosticar_relacoes": _wrap_diagnosticar_relacoes,
        "diagnosticar_sistemas": _wrap_diagnosticar_sistemas,
        "verificar_readiness": handle_verificar_readiness,
    }
    _diag_profiles: dict[str, list[str] | None] = {
        "diagnosticar_espacos": None,
        "diagnosticar_psets": None,
        "diagnosticar_relacoes": ["energy_readiness", "compliance_readiness"],
        "diagnosticar_sistemas": ["budget_readiness", "compliance_readiness"],
        "verificar_readiness": None,
    }
    for name, handler in _diag_handlers.items():
        tool = _tool_meta[name]
        registry.register(
            name=name,
            handler=handler,
            schema=tool.input_schema,
            description=tool.description,
            profiles=_diag_profiles[name],
            category="readiness" if name == "verificar_readiness" else "diagnostic",
        )

    # --- Ferramentas integradas ao QualityPipeline ---
    _pipeline_handlers: dict[str, Any] = {
        "iniciar_pipeline": handle_iniciar_pipeline,
        "progresso_sugestoes": handle_progresso_sugestoes,
        "listar_issues": handle_listar_issues,
        "obter_contexto_issue": handle_obter_contexto_issue,
        "listar_sugestoes": handle_listar_sugestoes,
        "explicar_sugestao": handle_explicar_sugestao,
        "aplicar_sugestao": handle_aplicar_sugestao,
        "pos_validar_issue": handle_pos_validar_issue,
        "exportar_artefatos": handle_exportar_artefatos,
        "fechar_pipeline": handle_fechar_pipeline,
    }
    for tool in PIPELINE_TOOLS:
        registry.register(
            name=tool.name,
            handler=_pipeline_handlers[tool.name],
            schema=tool.input_schema,
            description=tool.description,
            profiles=None,
            category="pipeline",
        )

    # --- Ferramentas de escrita ---
    _write_handlers: dict[str, Any] = {
        "renomear_espaco": handle_renomear_espaco,
        "preencher_pset": handle_preencher_pset,
        "criar_relacao_fills": handle_criar_relacao_fills,
        "classificar_sistema": handle_classificar_sistema,
        "preencher_base_quantities": handle_preencher_base_quantities,
        "mapear_classificacao": handle_mapear_classificacao,
        "associar_zona_termica": handle_associar_zona_termica,
        "registrar_log": handle_registrar_log,
    }
    _write_profiles: dict[str, list[str] | None] = {
        "renomear_espaco": None,
        "preencher_pset": None,
        "criar_relacao_fills": ["energy_readiness", "compliance_readiness"],
        "classificar_sistema": ["budget_readiness", "compliance_readiness"],
        "preencher_base_quantities": ["budget_readiness"],
        "mapear_classificacao": ["budget_readiness"],
        "associar_zona_termica": ["energy_readiness"],
        "registrar_log": None,
    }
    for tool in WRITE_TOOLS:
        registry.register(
            name=tool.name,
            handler=_write_handlers[tool.name],
            schema=tool.input_schema,
            description=tool.description,
            profiles=_write_profiles[tool.name],
            category="write",
        )

    return registry


_TOOL_REGISTRY = _build_registry()
_session["tool_registry"] = _TOOL_REGISTRY


# ---------------------------------------------------------------------------
# MCP handlers
# ---------------------------------------------------------------------------

async def list_tools() -> list[types.Tool]:
    """Lista todas as ferramentas disponíveis no servidor (sem filtro de perfil)."""
    return [
        types.Tool(
            name=e["name"],
            description=e["description"],
            inputSchema=e["schema"],
        )
        for e in _TOOL_REGISTRY.get_tools_for_profile(None)
    ]


async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Dispatcher principal — delega ao ToolRegistry."""
    entry = _TOOL_REGISTRY.get_tool(name)
    if entry is None:
        raise ValueError(f"Tool desconhecida: '{name}'")
    return await entry["handler"](_session, arguments)


async def _handle_list_tools_request(
    _context: Any,
    _params: types.PaginatedRequestParams,
) -> types.ListToolsResult:
    """Adapta o dispatcher interno ao contrato de transporte do MCP 2.x."""
    return types.ListToolsResult(tools=await list_tools())


async def _handle_call_tool_request(
    _context: Any,
    params: types.CallToolRequestParams,
) -> types.CallToolResult:
    """Adapta os parâmetros tipados do MCP 2.x ao ToolRegistry do projeto."""
    return types.CallToolResult(
        content=await call_tool(params.name, params.arguments or {}),
    )


server.add_request_handler(
    "tools/list",
    types.PaginatedRequestParams,
    _handle_list_tools_request,
)
server.add_request_handler(
    "tools/call",
    types.CallToolRequestParams,
    _handle_call_tool_request,
)


async def _main() -> None:
    """Inicializa o servidor MCP via transporte stdio."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(_main())
