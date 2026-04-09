"""Tools de diagnóstico (somente leitura) do MCP server."""

from typing import Any

import mcp.types as types
from loguru import logger

from src.ifc_analyzer import IFCAnalyzer
from src.models import Issue, ReadinessScore
from src.profiles.registry import create_default_registry


def _no_model_error() -> list[types.TextContent]:
    """Retorna resposta de erro padrão quando nenhum modelo está carregado."""
    from src.mcp_server.server import _json_response
    return _json_response({
        "sucesso": False,
        "erro": "Nenhum modelo carregado. Use 'carregar_modelo' primeiro.",
    })


def _get_analyzer(session: dict) -> IFCAnalyzer | None:
    """Retorna o IFCAnalyzer da sessão ou None se não carregado."""
    return session.get("analyzer")


# ---------------------------------------------------------------------------
# Serialização de issues por tipo
# ---------------------------------------------------------------------------

def _serialize_space_issue(issue: Issue) -> dict[str, Any]:
    """Serializa issue do tipo space_unnamed para o formato de resposta."""
    ctx = issue.context
    contained: list[str] = [
        el.get("functional_label") or el.get("name") or el.get("ifc_class", "")
        for el in ctx.get("contained_elements", [])
        if el.get("functional_label") or el.get("name")
    ]
    adjacencias: list[dict[str, str]] = [
        {"nome": adj.get("name", ""), "via": adj.get("connection_type", "")}
        for adj in ctx.get("adjacent_spaces", [])
    ]
    return {
        "issue_id": issue.id,
        "guid": issue.element_guid,
        "nome_atual": issue.element_name,
        "area_m2": ctx.get("area_m2"),
        "elementos_contidos": contained,
        "adjacencias": adjacencias,
        "severidade": issue.severity,
    }


def _serialize_pset_issue(issue: Issue) -> dict[str, Any]:
    """Serializa issue do tipo pset_missing para o formato de resposta."""
    ctx = issue.context
    return {
        "issue_id": issue.id,
        "guid": issue.element_guid,
        "classe": issue.element_class,
        "nome": issue.element_name,
        "pset_requerido": ctx.get("pset_name"),
        "propriedade_faltante": ctx.get("check_property"),
        "material": ctx.get("material_name"),
        "espessura_m": ctx.get("thickness_m"),
        "is_external": ctx.get("is_external"),
        "psets_existentes": ctx.get("existing_psets"),
        "severidade": issue.severity,
        "descricao": issue.description,
    }


def _serialize_relation_issue(issue: Issue) -> dict[str, Any]:
    """Serializa issue do tipo relation_broken para o formato de resposta."""
    ctx = issue.context
    return {
        "issue_id": issue.id,
        "guid": issue.element_guid,
        "classe": issue.element_class,
        "nome": issue.element_name,
        "relacao_esperada": ctx.get("expected_relation"),
        "parede_hospedeira": ctx.get("wall_host_guid"),
        "espacos_proximos": ctx.get("nearby_spaces"),
        "severidade": issue.severity,
        "descricao": issue.description,
    }


def _serialize_system_issue(issue: Issue) -> dict[str, Any]:
    """Serializa issue do tipo system_unclassified para o formato de resposta."""
    ctx = issue.context
    return {
        "issue_id": issue.id,
        "guid": issue.element_guid,
        "classe": issue.element_class,
        "nome": issue.element_name,
        "materiais": ctx.get("materials"),
        "espessura_total_m": ctx.get("total_thickness"),
        "classificacao_atual": ctx.get("classification_current"),
        "tem_pset_material_padrao": ctx.get("has_standard_material_pset"),
        "tem_pset_material_customizado": ctx.get("has_custom_pset_material"),
        "severidade": issue.severity,
        "descricao": issue.description,
    }


# ---------------------------------------------------------------------------
# Handlers das tools
# ---------------------------------------------------------------------------

async def handle_diagnosticar_espacos(session: dict) -> list[types.TextContent]:
    """Implementação da tool diagnosticar_espacos."""
    from src.mcp_server.server import _json_response

    analyzer = _get_analyzer(session)
    if analyzer is None:
        return _no_model_error()

    logger.info("Executando diagnóstico de espaços")
    issues = analyzer.analyze_spaces_only()

    total_espacos = len(analyzer.ifc_file.by_type("IfcSpace"))
    serialized = [_serialize_space_issue(i) for i in issues]

    return _json_response({
        "total_espacos": total_espacos,
        "espacos_problematicos": len(issues),
        "issues": serialized,
    })


async def handle_diagnosticar_psets(
    session: dict, arguments: dict
) -> list[types.TextContent]:
    """Implementação da tool diagnosticar_psets."""
    from src.mcp_server.server import _json_response

    analyzer = _get_analyzer(session)
    if analyzer is None:
        return _no_model_error()

    classes_filtro: list[str] | None = arguments.get("classes")

    logger.info(f"Executando diagnóstico de Psets (filtro de classes: {classes_filtro})")
    issues = analyzer.analyze_psets_only()

    if classes_filtro:
        issues = [i for i in issues if i.element_class in classes_filtro]

    por_classe: dict[str, int] = {}
    for issue in issues:
        por_classe[issue.element_class] = por_classe.get(issue.element_class, 0) + 1

    serialized = [_serialize_pset_issue(i) for i in issues]

    return _json_response({
        "total_issues": len(issues),
        "issues_por_classe": por_classe,
        "issues": serialized,
    })


async def handle_diagnosticar_relacoes(session: dict) -> list[types.TextContent]:
    """Implementação da tool diagnosticar_relacoes."""
    from src.mcp_server.server import _json_response

    analyzer = _get_analyzer(session)
    if analyzer is None:
        return _no_model_error()

    logger.info("Executando diagnóstico de relações espaciais")
    issues = analyzer.analyze_relations_only()

    por_tipo: dict[str, int] = {}
    for issue in issues:
        ctx_tipo = issue.context.get("expected_relation", "desconhecido")
        por_tipo[ctx_tipo] = por_tipo.get(ctx_tipo, 0) + 1

    serialized = [_serialize_relation_issue(i) for i in issues]

    return _json_response({
        "total_issues": len(issues),
        "issues_por_relacao": por_tipo,
        "issues": serialized,
    })


async def handle_verificar_readiness(
    session: dict, arguments: dict
) -> list[types.TextContent]:
    """Implementação da tool verificar_readiness."""
    from src.mcp_server.server import _json_response

    analyzer = _get_analyzer(session)
    if analyzer is None:
        return _no_model_error()

    profile_id: str = arguments["profile_id"]

    registry = create_default_registry()
    profile = registry.get(profile_id)
    if profile is None:
        available = [p.id for p in registry.list_profiles()]
        return _json_response({
            "sucesso": False,
            "erro": f"Perfil '{profile_id}' não encontrado.",
            "perfis_disponiveis": available,
        })

    logger.info("verificar_readiness: perfil='{}' modelo='{}'", profile_id, analyzer.model_name)

    try:
        report = analyzer.analyze()
    except Exception as exc:
        logger.error("verificar_readiness: falha no diagnóstico — {}", exc)
        return _json_response({"sucesso": False, "erro": f"Falha no diagnóstico: {exc}"})

    relevant_issues = [i for i in report.issues if i.issue_type in profile.issue_types]
    total_checks = report.total_issues if report.total_issues > 0 else 1

    score: ReadinessScore = ReadinessScore.compute(
        profile=profile,
        issues=relevant_issues,
        total_checks=total_checks,
    )

    return _json_response(score.model_dump())


async def handle_diagnosticar_sistemas(session: dict) -> list[types.TextContent]:
    """Implementação da tool diagnosticar_sistemas."""
    from src.mcp_server.server import _json_response

    analyzer = _get_analyzer(session)
    if analyzer is None:
        return _no_model_error()

    logger.info("Executando diagnóstico de sistemas construtivos")
    issues = analyzer.analyze_systems_only()

    por_classe: dict[str, int] = {}
    for issue in issues:
        por_classe[issue.element_class] = por_classe.get(issue.element_class, 0) + 1

    serialized = [_serialize_system_issue(i) for i in issues]

    return _json_response({
        "total_issues": len(issues),
        "issues_por_classe": por_classe,
        "issues": serialized,
    })


async def handle_listar_tools_disponiveis(
    session: dict, arguments: dict
) -> list[types.TextContent]:
    """Implementação da tool listar_tools_disponiveis."""
    from src.mcp_server.server import _json_response

    registry = session.get("tool_registry")
    if registry is None:
        return _json_response({"sucesso": False, "erro": "ToolRegistry não disponível na sessão."})

    profile_id: str | None = arguments.get("profile_id") or session.get("profile_id")

    entries = registry.get_tools_for_profile(profile_id)
    tools_info = [
        {
            "name": e["name"],
            "category": e["category"],
            "description": e["description"],
            "profiles": e["profiles"],
        }
        for e in entries
    ]

    return _json_response({
        "profile_id": profile_id,
        "total": len(tools_info),
        "tools": tools_info,
    })


# ---------------------------------------------------------------------------
# Definições das tools para list_tools()
# ---------------------------------------------------------------------------

DIAGNOSTIC_TOOLS = [
    types.Tool(
        name="diagnosticar_espacos",
        description=(
            "Analisa todos os IfcSpaces do modelo e identifica aqueles com nomes genéricos "
            "(Room 1, Room 2, etc). Retorna lista de espaços problemáticos com área, "
            "elementos contidos e adjacências para auxiliar na classificação funcional."
        ),
        inputSchema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
    types.Tool(
        name="diagnosticar_psets",
        description=(
            "Verifica propriedades obrigatórias (ThermalTransmittance, FireRating, IsExternal, etc) "
            "em paredes, portas, janelas, lajes e espaços. Retorna lista de propriedades faltantes "
            "com contexto do elemento (material, espessura). "
            "Use o parâmetro 'classes' para filtrar por tipo de elemento IFC, "
            "ex: ['IfcWall', 'IfcDoor']."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "classes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Lista de classes IFC para filtrar, ex: ['IfcWall', 'IfcDoor']. "
                        "Se omitido, retorna issues de todas as classes."
                    ),
                }
            },
            "required": [],
        },
    ),
    types.Tool(
        name="diagnosticar_relacoes",
        description=(
            "Verifica se portas e janelas possuem relação IfcRelFillsElement com sua parede "
            "hospedeira e se elementos estão contidos em espaços. "
            "Identifica relações espaciais quebradas."
        ),
        inputSchema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
    types.Tool(
        name="diagnosticar_sistemas",
        description=(
            "Verifica se paredes e lajes possuem classificação de sistema construtivo. "
            "Extrai informações de material e identifica quando dados estão em Psets customizados "
            "em vez de Psets IFC padrão."
        ),
        inputSchema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
    types.Tool(
        name="verificar_readiness",
        description=(
            "Calcula o score de readiness do modelo para um perfil específico. "
            "Perfis disponíveis: budget_readiness, energy_readiness, fm_readiness, compliance_readiness. "
            "Retorna total de verificações, issues bloqueantes, percentual de conformidade e status "
            "(ready, partially_ready, not_ready)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "profile_id": {
                    "type": "string",
                    "enum": [
                        "budget_readiness",
                        "energy_readiness",
                        "fm_readiness",
                        "compliance_readiness",
                    ],
                    "description": (
                        "Identificador do perfil de readiness a verificar. "
                        "budget_readiness: quantitativos e classificação orçamentária. "
                        "energy_readiness: simulação energética e envoltória. "
                        "fm_readiness: operação e manutenção. "
                        "compliance_readiness: checagem normativa NBR 15575."
                    ),
                }
            },
            "required": ["profile_id"],
        },
    ),
    types.Tool(
        name="listar_tools_disponiveis",
        description=(
            "Lista as ferramentas MCP disponíveis para o perfil de readiness informado. "
            "Use profile_id para filtrar por perfil (budget_readiness, energy_readiness, "
            "fm_readiness, compliance_readiness). Se omitido, usa o perfil ativo na sessão. "
            "Retorna nome, categoria e descrição de cada tool relevante."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "profile_id": {
                    "type": "string",
                    "enum": [
                        "budget_readiness",
                        "energy_readiness",
                        "fm_readiness",
                        "compliance_readiness",
                    ],
                    "description": "Perfil para filtrar tools. Se omitido, usa o perfil ativo na sessão.",
                }
            },
            "required": [],
        },
    ),
]
