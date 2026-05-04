"""Tools de escrita do MCP server — aplicam correções no modelo IFC após aprovação humana."""

from typing import Any

import mcp.types as types
from loguru import logger

from src.audit.logger import AuditLogger
from src.writer.ifc_writer import IFCWriter


def _approval_error() -> list[types.TextContent]:
    """Retorna erro padrão quando aprovação do usuário está ausente ou é False."""
    from src.mcp_server.server import _json_response
    return _json_response({"sucesso": False, "erro": "Operação requer aprovação do usuário"})


def _no_model_error() -> list[types.TextContent]:
    """Retorna erro padrão quando nenhum modelo está carregado na sessão."""
    from src.mcp_server.server import _json_response
    return _json_response({
        "sucesso": False,
        "erro": "Nenhum modelo carregado. Use 'carregar_modelo' primeiro.",
    })


def _get_writer(session: dict) -> IFCWriter | None:
    """Retorna o IFCWriter da sessão ou None se não disponível."""
    return session.get("writer")


def _get_audit_logger(session: dict) -> AuditLogger | None:
    """Retorna o AuditLogger da sessão ou None se não disponível."""
    return session.get("audit_logger")


# ---------------------------------------------------------------------------
# Handlers das tools
# ---------------------------------------------------------------------------

async def handle_renomear_espaco(
    session: dict, arguments: dict
) -> list[types.TextContent]:
    """Implementação da tool renomear_espaco."""
    from src.mcp_server.server import _json_response

    if not arguments.get("aprovado_pelo_usuario"):
        return _approval_error()

    writer = _get_writer(session)
    if writer is None:
        return _no_model_error()

    guid: str = arguments["guid"]
    novo_nome: str = arguments["novo_nome"]

    try:
        alterado, nome_anterior = writer.renomear_espaco(guid, novo_nome)
    except (ValueError, TypeError) as exc:
        logger.warning("renomear_espaco: erro — {}", exc)
        return _json_response({"sucesso": False, "erro": str(exc)})

    if not alterado:
        return _json_response({
            "sucesso": True,
            "guid": guid,
            "nome_anterior": novo_nome,
            "nome_novo": novo_nome,
            "aviso": "Nome já era igual ao solicitado, nenhuma alteração feita.",
        })

    logger.info("renomear_espaco: guid={} '{}' → '{}'", guid, nome_anterior, novo_nome)
    return _json_response({
        "sucesso": True,
        "guid": guid,
        "nome_anterior": nome_anterior,
        "nome_novo": novo_nome,
    })


async def handle_preencher_pset(
    session: dict, arguments: dict
) -> list[types.TextContent]:
    """Implementação da tool preencher_pset."""
    from src.mcp_server.server import _json_response

    if not arguments.get("aprovado_pelo_usuario"):
        return _approval_error()

    writer = _get_writer(session)
    if writer is None:
        return _no_model_error()

    guid: str = arguments["guid"]
    pset_name: str = arguments["pset_name"]
    propriedades: dict[str, Any] = arguments["propriedades"]

    try:
        _, valores_anteriores = writer.preencher_pset(guid, pset_name, propriedades)
    except (ValueError, TypeError) as exc:
        logger.warning("preencher_pset: erro — {}", exc)
        return _json_response({"sucesso": False, "erro": str(exc)})

    logger.info("preencher_pset: guid={} pset={}", guid, pset_name)
    return _json_response({
        "sucesso": True,
        "guid": guid,
        "pset": pset_name,
        "valores_anteriores": valores_anteriores,
        "valores_novos": propriedades,
    })


async def handle_criar_relacao_fills(
    session: dict, arguments: dict
) -> list[types.TextContent]:
    """Implementação da tool criar_relacao_fills."""
    from src.mcp_server.server import _json_response

    if not arguments.get("aprovado_pelo_usuario"):
        return _approval_error()

    writer = _get_writer(session)
    if writer is None:
        return _no_model_error()

    door_guid: str = arguments["door_guid"]
    wall_guid: str = arguments["wall_guid"]

    try:
        criado, _ = writer.criar_relacao_fills(door_guid, wall_guid)
    except (ValueError, TypeError) as exc:
        logger.warning("criar_relacao_fills: erro — {}", exc)
        return _json_response({"sucesso": False, "erro": str(exc)})

    if not criado:
        return _json_response({
            "sucesso": True,
            "porta": door_guid,
            "parede": wall_guid,
            "aviso": "Relação IfcRelFillsElement já existia, nenhuma alteração feita.",
        })

    logger.info("criar_relacao_fills: door={} wall={}", door_guid, wall_guid)
    return _json_response({
        "sucesso": True,
        "porta": door_guid,
        "parede": wall_guid,
    })


async def handle_classificar_sistema(
    session: dict, arguments: dict
) -> list[types.TextContent]:
    """Implementação da tool classificar_sistema."""
    from src.mcp_server.server import _json_response

    if not arguments.get("aprovado_pelo_usuario"):
        return _approval_error()

    writer = _get_writer(session)
    if writer is None:
        return _no_model_error()

    element_guid: str = arguments["element_guid"]
    sistema: str = arguments["sistema"]

    try:
        _, sistema_anterior = writer.classificar_sistema(element_guid, sistema)
    except (ValueError, TypeError) as exc:
        logger.warning("classificar_sistema: erro — {}", exc)
        return _json_response({"sucesso": False, "erro": str(exc)})

    logger.info("classificar_sistema: guid={} sistema='{}'", element_guid, sistema)
    return _json_response({
        "sucesso": True,
        "guid": element_guid,
        "sistema": sistema,
        "sistema_anterior": sistema_anterior,
    })


async def handle_preencher_base_quantities(
    session: dict, arguments: dict
) -> list[types.TextContent]:
    """Implementação da tool preencher_base_quantities."""
    from src.mcp_server.server import _json_response

    if not arguments.get("aprovado_pelo_usuario"):
        return _approval_error()

    writer = _get_writer(session)
    if writer is None:
        return _no_model_error()

    guid: str = arguments["guid"]
    qto_name: str = arguments["qto_name"]
    quantities: dict = arguments["quantities"]

    try:
        _, valores_anteriores = writer.preencher_base_quantities(guid, qto_name, quantities)
    except (ValueError, TypeError) as exc:
        logger.warning("preencher_base_quantities: erro — {}", exc)
        return _json_response({"sucesso": False, "erro": str(exc)})

    logger.info("preencher_base_quantities: guid={} qto={}", guid, qto_name)
    return _json_response({
        "sucesso": True,
        "guid": guid,
        "qto_name": qto_name,
        "quantities_preenchidas": list(quantities.keys()),
        "valores_anteriores": valores_anteriores,
    })


async def handle_mapear_classificacao(
    session: dict, arguments: dict
) -> list[types.TextContent]:
    """Implementação da tool mapear_classificacao."""
    from src.mcp_server.server import _json_response

    if not arguments.get("aprovado_pelo_usuario"):
        return _approval_error()

    writer = _get_writer(session)
    if writer is None:
        return _no_model_error()

    guid: str = arguments["guid"]
    sistema: str = arguments["sistema"]
    codigo: str = arguments["codigo"]
    descricao: str = arguments["descricao"]

    try:
        _, classificacao_anterior = writer.mapear_classificacao(guid, sistema, codigo, descricao)
    except (ValueError, TypeError) as exc:
        logger.warning("mapear_classificacao: erro — {}", exc)
        return _json_response({"sucesso": False, "erro": str(exc)})

    logger.info("mapear_classificacao: guid={} sistema='{}' codigo='{}'", guid, sistema, codigo)
    return _json_response({
        "sucesso": True,
        "guid": guid,
        "sistema": sistema,
        "codigo": codigo,
        "classificacao_anterior": classificacao_anterior,
    })


async def handle_associar_zona_termica(
    session: dict, arguments: dict
) -> list[types.TextContent]:
    """Implementação da tool associar_zona_termica."""
    from src.mcp_server.server import _json_response

    if not arguments.get("aprovado_pelo_usuario"):
        return _approval_error()

    writer = _get_writer(session)
    if writer is None:
        return _no_model_error()

    space_guid: str = arguments["space_guid"]
    zone_name: str = arguments["zone_name"]
    zone_type: str = arguments.get("zone_type", "thermal")

    try:
        adicionado, _ = writer.associar_zona_termica(space_guid, zone_name, zone_type)
    except (ValueError, TypeError) as exc:
        logger.warning("associar_zona_termica: erro — {}", exc)
        return _json_response({"sucesso": False, "erro": str(exc)})

    if not adicionado:
        return _json_response({
            "sucesso": True,
            "space_guid": space_guid,
            "zone": {"name": zone_name, "type": zone_type},
            "aviso": "Espaço já pertencia à zona, nenhuma alteração feita.",
        })

    logger.info("associar_zona_termica: space={} zona='{}'", space_guid, zone_name)
    return _json_response({
        "sucesso": True,
        "space_guid": space_guid,
        "zone": {"name": zone_name, "type": zone_type},
    })


async def handle_registrar_log(
    session: dict, arguments: dict
) -> list[types.TextContent]:
    """Implementação da tool registrar_log — registra ação no AuditLogger da sessão."""
    from src.mcp_server.server import _json_response

    audit_logger = _get_audit_logger(session)
    if audit_logger is None:
        return _json_response({"registrado": False, "erro": "AuditLogger não disponível na sessão."})

    guid: str = arguments["guid"]
    acao: str = arguments["acao"]
    valor_anterior: Any = arguments.get("valor_anterior")
    valor_novo: Any = arguments.get("valor_novo")
    decisao: str = arguments["decisao"]
    referencia: str | None = arguments.get("referencia")
    usuario: str = arguments.get("usuario", "engineer")

    # Tenta obter element_class real a partir do modelo carregado
    element_class = "unknown"
    analyzer = session.get("analyzer")
    if analyzer is not None:
        try:
            element = analyzer.ifc_file.by_guid(guid)
            element_class = element.is_a()
        except Exception:
            pass

    audit_logger.log_simples(
        guid=guid,
        acao=acao,
        valor_anterior=valor_anterior,
        valor_novo=valor_novo,
        decisao=decisao,  # type: ignore[arg-type]
        referencia=referencia,
        usuario=usuario,
        element_class=element_class,
    )

    return _json_response({"registrado": True})


# ---------------------------------------------------------------------------
# Definições das tools para list_tools()
# ---------------------------------------------------------------------------

WRITE_TOOLS = [
    types.Tool(
        name="renomear_espaco",
        description=(
            "Renomeia o LongName de um IfcSpace no modelo carregado. "
            "Requer aprovação explícita do usuário (aprovado_pelo_usuario: true). "
            "Retorna o nome anterior e o nome novo após a alteração."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "guid": {
                    "type": "string",
                    "description": "GlobalId (22 caracteres) do IfcSpace a ser renomeado.",
                },
                "novo_nome": {
                    "type": "string",
                    "description": "Novo LongName para o espaço, ex: 'Lavabo Suíte'.",
                },
                "aprovado_pelo_usuario": {
                    "type": "boolean",
                    "description": "Deve ser true para executar a operação. Se false, retorna erro.",
                },
            },
            "required": ["guid", "novo_nome", "aprovado_pelo_usuario"],
        },
    ),
    types.Tool(
        name="preencher_pset",
        description=(
            "Cria ou atualiza propriedades em um Property Set (Pset) de um elemento IFC. "
            "Requer aprovação explícita do usuário (aprovado_pelo_usuario: true). "
            "Retorna os valores anteriores e os valores novos escritos no modelo."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "guid": {
                    "type": "string",
                    "description": "GlobalId (22 caracteres) do elemento IFC.",
                },
                "pset_name": {
                    "type": "string",
                    "description": "Nome do PropertySet, ex: 'Pset_WallCommon'.",
                },
                "propriedades": {
                    "type": "object",
                    "description": (
                        "Dicionário de propriedades a escrever, ex: "
                        "{\"ThermalTransmittance\": 2.5, \"IsExternal\": true}."
                    ),
                },
                "aprovado_pelo_usuario": {
                    "type": "boolean",
                    "description": "Deve ser true para executar a operação. Se false, retorna erro.",
                },
            },
            "required": ["guid", "pset_name", "propriedades", "aprovado_pelo_usuario"],
        },
    ),
    types.Tool(
        name="criar_relacao_fills",
        description=(
            "Cria uma relação IfcRelFillsElement entre uma porta ou janela e a parede hospedeira. "
            "Requer aprovação explícita do usuário (aprovado_pelo_usuario: true). "
            "Cria automaticamente um IfcOpeningElement se não existir abertura disponível na parede."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "door_guid": {
                    "type": "string",
                    "description": "GlobalId (22 caracteres) do IfcDoor ou IfcWindow.",
                },
                "wall_guid": {
                    "type": "string",
                    "description": "GlobalId (22 caracteres) da IfcWall hospedeira.",
                },
                "aprovado_pelo_usuario": {
                    "type": "boolean",
                    "description": "Deve ser true para executar a operação. Se false, retorna erro.",
                },
            },
            "required": ["door_guid", "wall_guid", "aprovado_pelo_usuario"],
        },
    ),
    types.Tool(
        name="classificar_sistema",
        description=(
            "Adiciona ou atualiza a classificação de sistema construtivo em uma parede ou laje. "
            "Requer aprovação explícita do usuário (aprovado_pelo_usuario: true). "
            "Usa a classificação 'Sistema Construtivo' por padrão. "
            "Retorna o sistema atribuído e o sistema anterior, se houver."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "element_guid": {
                    "type": "string",
                    "description": "GlobalId (22 caracteres) do elemento IFC (IfcWall, IfcSlab, etc.).",
                },
                "sistema": {
                    "type": "string",
                    "description": "Nome do sistema construtivo, ex: 'Alvenaria de Vedação', 'Concreto Armado'.",
                },
                "aprovado_pelo_usuario": {
                    "type": "boolean",
                    "description": "Deve ser true para executar a operação. Se false, retorna erro.",
                },
            },
            "required": ["element_guid", "sistema", "aprovado_pelo_usuario"],
        },
    ),
    types.Tool(
        name="preencher_base_quantities",
        description=(
            "Preenche ou atualiza BaseQuantities (Qto_*) de um elemento IFC. "
            "Útil para corrigir modelos sem quantitativos exportados. "
            "Aceita múltiplas quantities de uma vez. "
            "Requer aprovação explícita do usuário (aprovado_pelo_usuario: true)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "guid": {
                    "type": "string",
                    "description": "GlobalId (22 caracteres) do elemento IFC.",
                },
                "qto_name": {
                    "type": "string",
                    "description": "Nome do IfcElementQuantity, ex: 'Qto_WallBaseQuantities'.",
                },
                "quantities": {
                    "type": "object",
                    "description": (
                        "Dicionário de quantidades a escrever, ex: "
                        "{\"GrossArea\": 12.5, \"Length\": 3.0, \"Volume\": 0.375}. "
                        "O tipo IFC é inferido pelo sufixo do nome (Area, Length, Volume, Count)."
                    ),
                },
                "aprovado_pelo_usuario": {
                    "type": "boolean",
                    "description": "Deve ser true para executar a operação. Se false, retorna erro.",
                },
            },
            "required": ["guid", "qto_name", "quantities", "aprovado_pelo_usuario"],
        },
    ),
    types.Tool(
        name="mapear_classificacao",
        description=(
            "Associa um elemento a uma classificação orçamentária (SINAPI, TCPO, Omniclass, etc). "
            "Cria ou atualiza IfcClassificationReference. "
            "Requer aprovação explícita do usuário (aprovado_pelo_usuario: true)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "guid": {
                    "type": "string",
                    "description": "GlobalId (22 caracteres) do elemento IFC.",
                },
                "sistema": {
                    "type": "string",
                    "description": "Nome do sistema de classificação, ex: 'SINAPI', 'TCPO', 'Omniclass'.",
                },
                "codigo": {
                    "type": "string",
                    "description": "Código de identificação no sistema, ex: '87878', '73.10.050'.",
                },
                "descricao": {
                    "type": "string",
                    "description": "Descrição legível da classificação, ex: 'Alvenaria de vedação em bloco cerâmico'.",
                },
                "aprovado_pelo_usuario": {
                    "type": "boolean",
                    "description": "Deve ser true para executar a operação. Se false, retorna erro.",
                },
            },
            "required": ["guid", "sistema", "codigo", "descricao", "aprovado_pelo_usuario"],
        },
    ),
    types.Tool(
        name="associar_zona_termica",
        description=(
            "Associa um IfcSpace a uma IfcZone para zoneamento térmico ou HVAC. "
            "Cria a zona se não existir. "
            "Requer aprovação explícita do usuário (aprovado_pelo_usuario: true)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "space_guid": {
                    "type": "string",
                    "description": "GlobalId (22 caracteres) do IfcSpace a associar.",
                },
                "zone_name": {
                    "type": "string",
                    "description": "Nome da zona, ex: 'Zona Norte', 'HVAC-01'.",
                },
                "zone_type": {
                    "type": "string",
                    "description": "Tipo semântico da zona: 'thermal', 'hvac' ou 'lighting'. Padrão: 'thermal'.",
                    "default": "thermal",
                },
                "aprovado_pelo_usuario": {
                    "type": "boolean",
                    "description": "Deve ser true para executar a operação. Se false, retorna erro.",
                },
            },
            "required": ["space_guid", "zone_name", "aprovado_pelo_usuario"],
        },
    ),
    types.Tool(
        name="registrar_log",
        description=(
            "Registra manualmente uma ação de correção no audit trail da sessão. "
            "Use após aplicar uma correção para manter rastreabilidade completa. "
            "Não requer aprovado_pelo_usuario — o log é sempre permitido."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "guid": {
                    "type": "string",
                    "description": "GlobalId (22 caracteres) do elemento IFC afetado.",
                },
                "acao": {
                    "type": "string",
                    "description": "Nome da ação realizada, ex: 'renomear_espaco', 'preencher_pset'.",
                },
                "valor_anterior": {
                    "description": "Valor antes da correção (qualquer tipo).",
                },
                "valor_novo": {
                    "description": "Valor após a correção (qualquer tipo).",
                },
                "decisao": {
                    "type": "string",
                    "enum": ["accepted", "edited", "rejected"],
                    "description": "Decisão do engenheiro: accepted, edited ou rejected.",
                },
                "referencia": {
                    "type": "string",
                    "description": "Referência normativa usada, ex: 'NBR 15575-4 Tab. C.2'. Pode ser null.",
                },
                "usuario": {
                    "type": "string",
                    "description": "Identificador do usuário que tomou a decisão.",
                    "default": "engineer",
                },
            },
            "required": ["guid", "acao", "valor_novo", "decisao", "usuario"],
        },
    ),
]
