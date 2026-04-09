"""Testes para o MCP server — handlers de leitura e escrita.

Cada teste chama diretamente a função handler da tool (sem transporte MCP real),
verifica o JSON de retorno e os side effects no modelo IFC.
"""

import asyncio
import json
from unittest.mock import patch

import ifcopenshell.util.element
import pytest

from src.audit.logger import AuditLogger
from src.ifc_analyzer import IFCAnalyzer
from src.writer.ifc_writer import IFCWriter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse(result) -> dict:
    """Extrai e desserializa o JSON retornado por um handler MCP."""
    return json.loads(result[0].text)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_ifc_path(tmp_path, complete_test_model):
    """Escreve o modelo de teste em arquivo temporário.

    Retorna (caminho_str, metadata).
    """
    f, metadata = complete_test_model
    ifc_path = str(tmp_path / "test_model.ifc")
    f.write(ifc_path)
    return ifc_path, metadata


@pytest.fixture
def mcp_session(tmp_ifc_path):
    """Cria sessão MCP com IFCAnalyzer, IFCWriter, AuditLogger e ToolRegistry.

    Retorna (session_dict, metadata).  O session_dict tem as chaves
    'analyzer', 'writer', 'audit_logger', 'profile_id' e 'tool_registry',
    idênticas às usadas pelo server.
    """
    from src.mcp_server.server import _TOOL_REGISTRY

    ifc_path, metadata = tmp_ifc_path
    analyzer = IFCAnalyzer(ifc_path)
    writer = IFCWriter(analyzer.ifc_file)
    audit_logger = AuditLogger()
    session = {
        "analyzer": analyzer,
        "writer": writer,
        "audit_logger": audit_logger,
        "profile_id": None,
        "tool_registry": _TOOL_REGISTRY,
    }
    return session, metadata


# ---------------------------------------------------------------------------
# carregar_modelo
# ---------------------------------------------------------------------------


def test_tool_carregar_modelo_success(tmp_ifc_path):
    """carregar_modelo com caminho válido retorna sucesso e metadados do modelo."""
    from src.mcp_server.server import _carregar_modelo

    ifc_path, _ = tmp_ifc_path
    result = asyncio.run(_carregar_modelo({"filepath": ifc_path}))
    data = _parse(result)

    assert data["sucesso"] is True
    assert "modelo" in data
    assert isinstance(data["total_elementos"], int)
    assert data["total_elementos"] >= 0
    assert "schema" in data


def test_tool_carregar_modelo_invalid_path(tmp_path):
    """carregar_modelo com caminho inexistente retorna sucesso=False e mensagem de erro."""
    from src.mcp_server.server import _carregar_modelo

    fake_path = str(tmp_path / "nao_existe.ifc")
    result = asyncio.run(_carregar_modelo({"filepath": fake_path}))
    data = _parse(result)

    assert data["sucesso"] is False
    assert "erro" in data
    assert "não encontrado" in data["erro"]


def test_tool_carregar_modelo_wrong_extension(tmp_path):
    """carregar_modelo com extensão incorreta retorna sucesso=False."""
    from src.mcp_server.server import _carregar_modelo

    txt_path = tmp_path / "arquivo.txt"
    txt_path.write_text("conteúdo qualquer")
    result = asyncio.run(_carregar_modelo({"filepath": str(txt_path)}))
    data = _parse(result)

    assert data["sucesso"] is False
    assert ".ifc" in data["erro"]


# ---------------------------------------------------------------------------
# resumo_modelo
# ---------------------------------------------------------------------------


def test_tool_resumo_modelo_returns_counts(mcp_session):
    """resumo_modelo retorna contagens por classe, schema e psets presentes."""
    import src.mcp_server.server as srv

    session, _ = mcp_session
    with patch.dict(srv._session, session):
        result = asyncio.run(srv._resumo_modelo())
    data = _parse(result)

    assert "nome" in data
    assert "schema" in data
    assert "total_elementos" in data
    assert "por_classe" in data
    assert "IfcWall" in data["por_classe"]
    assert "IfcSpace" in data["por_classe"]
    assert "psets_encontrados" in data
    assert isinstance(data["psets_encontrados"], list)


def test_tool_resumo_modelo_without_load_errors():
    """resumo_modelo sem modelo carregado retorna sucesso=False."""
    import src.mcp_server.server as srv

    with patch.dict(srv._session, {"analyzer": None}):
        result = asyncio.run(srv._resumo_modelo())
    data = _parse(result)

    assert data["sucesso"] is False
    assert "carregar_modelo" in data["erro"]


# ---------------------------------------------------------------------------
# diagnosticar_espacos
# ---------------------------------------------------------------------------


def test_tool_diagnosticar_espacos_returns_issues(mcp_session):
    """diagnosticar_espacos retorna total de espaços e lista de issues."""
    from src.mcp_server.tools_read import handle_diagnosticar_espacos

    session, _ = mcp_session
    result = asyncio.run(handle_diagnosticar_espacos(session))
    data = _parse(result)

    assert "total_espacos" in data
    assert "espacos_problematicos" in data
    assert isinstance(data["issues"], list)
    assert data["espacos_problematicos"] == len(data["issues"])


def test_tool_diagnosticar_espacos_no_model():
    """diagnosticar_espacos sem modelo carregado retorna erro padrão."""
    from src.mcp_server.tools_read import handle_diagnosticar_espacos

    result = asyncio.run(handle_diagnosticar_espacos({"analyzer": None}))
    data = _parse(result)

    assert data["sucesso"] is False
    assert "carregar_modelo" in data["erro"]


# ---------------------------------------------------------------------------
# diagnosticar_psets
# ---------------------------------------------------------------------------


def test_tool_diagnosticar_psets_returns_issues(mcp_session):
    """diagnosticar_psets retorna total de issues e agrupamento por classe."""
    from src.mcp_server.tools_read import handle_diagnosticar_psets

    session, _ = mcp_session
    result = asyncio.run(handle_diagnosticar_psets(session, {}))
    data = _parse(result)

    assert "total_issues" in data
    assert "issues_por_classe" in data
    assert isinstance(data["issues"], list)
    assert data["total_issues"] == len(data["issues"])


def test_tool_diagnosticar_psets_returns_issues_with_class_filter(mcp_session):
    """diagnosticar_psets com filtro retorna apenas issues da classe informada."""
    from src.mcp_server.tools_read import handle_diagnosticar_psets

    session, _ = mcp_session
    result = asyncio.run(handle_diagnosticar_psets(session, {"classes": ["IfcWall"]}))
    data = _parse(result)

    for issue in data["issues"]:
        assert issue["classe"] == "IfcWall"


def test_tool_diagnosticar_psets_no_model():
    """diagnosticar_psets sem modelo carregado retorna erro."""
    from src.mcp_server.tools_read import handle_diagnosticar_psets

    result = asyncio.run(handle_diagnosticar_psets({"analyzer": None}, {}))
    data = _parse(result)

    assert data["sucesso"] is False


# ---------------------------------------------------------------------------
# diagnosticar_relacoes
# ---------------------------------------------------------------------------


def test_tool_diagnosticar_relacoes_returns_issues(mcp_session):
    """diagnosticar_relacoes retorna issues de relações quebradas com Door 2."""
    from src.mcp_server.tools_read import handle_diagnosticar_relacoes

    session, _ = mcp_session
    result = asyncio.run(handle_diagnosticar_relacoes(session))
    data = _parse(result)

    assert "total_issues" in data
    assert "issues_por_relacao" in data
    assert isinstance(data["issues"], list)
    # complete_test_model tem Door 2 sem IfcRelFillsElement
    assert data["total_issues"] >= 1


def test_tool_diagnosticar_relacoes_no_model():
    """diagnosticar_relacoes sem modelo carregado retorna erro."""
    from src.mcp_server.tools_read import handle_diagnosticar_relacoes

    result = asyncio.run(handle_diagnosticar_relacoes({"analyzer": None}))
    data = _parse(result)

    assert data["sucesso"] is False


# ---------------------------------------------------------------------------
# diagnosticar_sistemas
# ---------------------------------------------------------------------------


def test_tool_diagnosticar_sistemas_returns_issues(mcp_session):
    """diagnosticar_sistemas retorna issues agrupados por classe IFC."""
    from src.mcp_server.tools_read import handle_diagnosticar_sistemas

    session, _ = mcp_session
    result = asyncio.run(handle_diagnosticar_sistemas(session))
    data = _parse(result)

    assert "total_issues" in data
    assert "issues_por_classe" in data
    assert isinstance(data["issues"], list)


def test_tool_diagnosticar_sistemas_no_model():
    """diagnosticar_sistemas sem modelo carregado retorna erro."""
    from src.mcp_server.tools_read import handle_diagnosticar_sistemas

    result = asyncio.run(handle_diagnosticar_sistemas({"analyzer": None}))
    data = _parse(result)

    assert data["sucesso"] is False


# ---------------------------------------------------------------------------
# renomear_espaco
# ---------------------------------------------------------------------------


def test_tool_renomear_espaco_approved(mcp_session):
    """renomear_espaco com aprovação renomeia o LongName e retorna nome anterior."""
    from src.mcp_server.tools_write import handle_renomear_espaco

    session, meta = mcp_session
    guid = meta["space1_guid"]  # LongName original: "Room 1"
    args = {"guid": guid, "novo_nome": "Sala de Estar", "aprovado_pelo_usuario": True}

    result = asyncio.run(handle_renomear_espaco(session, args))
    data = _parse(result)

    assert data["sucesso"] is True
    assert data["guid"] == guid
    assert data["nome_anterior"] == "Room 1"
    assert data["nome_novo"] == "Sala de Estar"
    # Side effect: modelo deve refletir o novo nome
    espaco = session["analyzer"].ifc_file.by_guid(guid)
    assert espaco.LongName == "Sala de Estar"


def test_tool_renomear_espaco_not_approved_rejects(mcp_session):
    """renomear_espaco sem aprovação retorna erro sem alterar o modelo."""
    from src.mcp_server.tools_write import handle_renomear_espaco

    session, meta = mcp_session
    guid = meta["space1_guid"]
    nome_original = session["analyzer"].ifc_file.by_guid(guid).LongName

    args = {"guid": guid, "novo_nome": "Sala de Estar", "aprovado_pelo_usuario": False}
    result = asyncio.run(handle_renomear_espaco(session, args))
    data = _parse(result)

    assert data["sucesso"] is False
    assert "aprovação" in data["erro"]
    # Modelo não deve ter sido alterado
    assert session["analyzer"].ifc_file.by_guid(guid).LongName == nome_original


def test_tool_renomear_espaco_invalid_guid(mcp_session):
    """renomear_espaco com GUID inexistente retorna erro."""
    from src.mcp_server.tools_write import handle_renomear_espaco

    session, _ = mcp_session
    args = {
        "guid": "GUIDINVALIDOXXXXXXXXXX1",
        "novo_nome": "Novo Nome",
        "aprovado_pelo_usuario": True,
    }
    result = asyncio.run(handle_renomear_espaco(session, args))
    data = _parse(result)

    assert data["sucesso"] is False
    assert "erro" in data


# ---------------------------------------------------------------------------
# preencher_pset
# ---------------------------------------------------------------------------


def test_tool_preencher_pset_approved(mcp_session):
    """preencher_pset com aprovação atualiza propriedade no Pset do elemento."""
    from src.mcp_server.tools_write import handle_preencher_pset

    session, meta = mcp_session
    guid = meta["wall1_guid"]  # Wall 1 com Pset_WallCommon (ThermalTransmittance=None)
    args = {
        "guid": guid,
        "pset_name": "Pset_WallCommon",
        "propriedades": {"ThermalTransmittance": 2.48},
        "aprovado_pelo_usuario": True,
    }

    result = asyncio.run(handle_preencher_pset(session, args))
    data = _parse(result)

    assert data["sucesso"] is True
    assert data["guid"] == guid
    assert data["pset"] == "Pset_WallCommon"
    assert data["valores_novos"] == {"ThermalTransmittance": 2.48}
    # Side effect: valor deve estar no modelo
    ifc_el = session["analyzer"].ifc_file.by_guid(guid)
    psets = ifcopenshell.util.element.get_psets(ifc_el)
    assert psets["Pset_WallCommon"]["ThermalTransmittance"] == pytest.approx(2.48)


def test_tool_preencher_pset_not_approved_rejects(mcp_session):
    """preencher_pset sem aprovação retorna erro sem modificar o modelo."""
    from src.mcp_server.tools_write import handle_preencher_pset

    session, meta = mcp_session
    args = {
        "guid": meta["wall1_guid"],
        "pset_name": "Pset_WallCommon",
        "propriedades": {"ThermalTransmittance": 99.0},
        "aprovado_pelo_usuario": False,
    }

    result = asyncio.run(handle_preencher_pset(session, args))
    data = _parse(result)

    assert data["sucesso"] is False
    assert "aprovação" in data["erro"]


# ---------------------------------------------------------------------------
# criar_relacao_fills
# ---------------------------------------------------------------------------


def test_tool_criar_relacao_approved(mcp_session):
    """criar_relacao_fills cria IfcRelFillsElement entre Door 2 (sem relação) e parede."""
    from src.mcp_server.tools_write import handle_criar_relacao_fills

    session, meta = mcp_session
    door_guid = meta["door2_guid"]  # Door 2 sem IfcRelFillsElement
    wall_guid = meta["wall1_guid"]
    args = {
        "door_guid": door_guid,
        "wall_guid": wall_guid,
        "aprovado_pelo_usuario": True,
    }

    result = asyncio.run(handle_criar_relacao_fills(session, args))
    data = _parse(result)

    assert data["sucesso"] is True
    assert data["porta"] == door_guid
    assert data["parede"] == wall_guid
    # Side effect: relação deve existir no modelo
    ifc_file = session["analyzer"].ifc_file
    door_el = ifc_file.by_guid(door_guid)
    fills = [
        rel
        for rel in ifc_file.by_type("IfcRelFillsElement")
        if rel.RelatedBuildingElement == door_el
    ]
    assert len(fills) == 1


def test_tool_criar_relacao_not_approved_rejects(mcp_session):
    """criar_relacao_fills sem aprovação retorna erro sem criar relação."""
    from src.mcp_server.tools_write import handle_criar_relacao_fills

    session, meta = mcp_session
    args = {
        "door_guid": meta["door2_guid"],
        "wall_guid": meta["wall1_guid"],
        "aprovado_pelo_usuario": False,
    }

    result = asyncio.run(handle_criar_relacao_fills(session, args))
    data = _parse(result)

    assert data["sucesso"] is False
    assert "aprovação" in data["erro"]


# ---------------------------------------------------------------------------
# classificar_sistema
# ---------------------------------------------------------------------------


def test_tool_classificar_sistema_approved(mcp_session):
    """classificar_sistema com aprovação adiciona IfcRelAssociatesClassification ao elemento."""
    from src.mcp_server.tools_write import handle_classificar_sistema

    session, meta = mcp_session
    wall_guid = meta["wall3_guid"]  # Wall 3 sem classificação de sistema
    args = {
        "element_guid": wall_guid,
        "sistema": "Alvenaria de Vedação",
        "aprovado_pelo_usuario": True,
    }

    result = asyncio.run(handle_classificar_sistema(session, args))
    data = _parse(result)

    assert data["sucesso"] is True
    assert data["guid"] == wall_guid
    assert data["sistema"] == "Alvenaria de Vedação"
    # Side effect: elemento deve ter classificação no modelo
    ifc_file = session["analyzer"].ifc_file
    wall_el = ifc_file.by_guid(wall_guid)
    has_classification = any(
        wall_el in rel.RelatedObjects
        for rel in ifc_file.by_type("IfcRelAssociatesClassification")
    )
    assert has_classification


def test_tool_classificar_sistema_not_approved_rejects(mcp_session):
    """classificar_sistema sem aprovação retorna erro."""
    from src.mcp_server.tools_write import handle_classificar_sistema

    session, meta = mcp_session
    args = {
        "element_guid": meta["wall3_guid"],
        "sistema": "Concreto Armado",
        "aprovado_pelo_usuario": False,
    }

    result = asyncio.run(handle_classificar_sistema(session, args))
    data = _parse(result)

    assert data["sucesso"] is False
    assert "aprovação" in data["erro"]


# ---------------------------------------------------------------------------
# registrar_log
# ---------------------------------------------------------------------------


def test_tool_registrar_log(mcp_session):
    """registrar_log adiciona entrada ao AuditLogger com os campos corretos."""
    from src.mcp_server.tools_write import handle_registrar_log

    session, meta = mcp_session
    guid = meta["wall1_guid"]
    args = {
        "guid": guid,
        "acao": "preencher_pset",
        "valor_anterior": None,
        "valor_novo": 2.48,
        "decisao": "accepted",
        "referencia": "NBR 15575-4",
        "usuario": "engineer",
    }

    result = asyncio.run(handle_registrar_log(session, args))
    data = _parse(result)

    assert data["registrado"] is True
    audit = session["audit_logger"]
    assert len(audit.entries) == 1
    entry = audit.entries[0]
    assert entry.element_guid == guid
    assert entry.action == "preencher_pset"
    assert entry.decision == "accepted"
    assert entry.normative_ref == "NBR 15575-4"
    assert entry.user == "engineer"


def test_tool_registrar_log_no_audit_logger(mcp_session):
    """registrar_log sem AuditLogger na sessão retorna registrado=False."""
    from src.mcp_server.tools_write import handle_registrar_log

    session, meta = mcp_session
    bad_session = {**session, "audit_logger": None}
    args = {
        "guid": meta["wall1_guid"],
        "acao": "preencher_pset",
        "valor_anterior": None,
        "valor_novo": 2.48,
        "decisao": "accepted",
        "usuario": "engineer",
    }

    result = asyncio.run(handle_registrar_log(bad_session, args))
    data = _parse(result)

    assert data["registrado"] is False
    assert "erro" in data


# ---------------------------------------------------------------------------
# ToolRegistry
# ---------------------------------------------------------------------------


def test_registry_register_and_get():
    """register() armazena tool e get_tool() retorna o dict correto."""
    from src.mcp_server.registry import ToolRegistry

    async def _handler(session, arguments):
        return []

    registry = ToolRegistry()
    registry.register(
        name="minha_tool",
        handler=_handler,
        schema={"type": "object", "properties": {}},
        description="Descrição da tool",
        profiles=["budget_readiness"],
        category="read",
    )

    entry = registry.get_tool("minha_tool")
    assert entry is not None
    assert entry["handler"] is _handler
    assert entry["category"] == "read"
    assert entry["profiles"] == ["budget_readiness"]
    assert registry.get_tool("inexistente") is None


def test_registry_filter_by_profile():
    """get_tools_for_profile() retorna apenas tools cujo profiles inclui o perfil."""
    from src.mcp_server.registry import ToolRegistry

    async def _h(s, a):
        return []

    registry = ToolRegistry()
    registry.register("tool_budget", _h, {}, profiles=["budget_readiness"], category="read")
    registry.register("tool_energy", _h, {}, profiles=["energy_readiness"], category="read")
    registry.register("tool_ambos", _h, {}, profiles=["budget_readiness", "energy_readiness"], category="read")

    budget_tools = [t["name"] for t in registry.get_tools_for_profile("budget_readiness")]
    assert "tool_budget" in budget_tools
    assert "tool_ambos" in budget_tools
    assert "tool_energy" not in budget_tools

    energy_tools = [t["name"] for t in registry.get_tools_for_profile("energy_readiness")]
    assert "tool_energy" in energy_tools
    assert "tool_ambos" in energy_tools
    assert "tool_budget" not in energy_tools


def test_registry_none_profile_returns_all():
    """get_tools_for_profile(None) retorna todas as tools, inclusive as com profiles=None."""
    from src.mcp_server.registry import ToolRegistry

    async def _h(s, a):
        return []

    registry = ToolRegistry()
    registry.register("tool_a", _h, {}, profiles=["budget_readiness"])
    registry.register("tool_b", _h, {}, profiles=None)  # disponível em todos
    registry.register("tool_c", _h, {}, profiles=["energy_readiness"])

    all_tools = [t["name"] for t in registry.get_tools_for_profile(None)]
    assert "tool_a" in all_tools
    assert "tool_b" in all_tools
    assert "tool_c" in all_tools


def test_tool_listar_disponiveis(mcp_session):
    """listar_tools_disponiveis retorna lista de tools para o perfil informado."""
    from src.mcp_server.tools_read import handle_listar_tools_disponiveis

    session, _ = mcp_session
    result = asyncio.run(handle_listar_tools_disponiveis(session, {"profile_id": "budget_readiness"}))
    data = _parse(result)

    assert "profile_id" in data
    assert data["profile_id"] == "budget_readiness"
    assert isinstance(data["tools"], list)
    assert len(data["tools"]) > 0

    nomes = [t["name"] for t in data["tools"]]
    # budget deve incluir diagnosticar_espacos e preencher_base_quantities
    assert "diagnosticar_espacos" in nomes
    assert "preencher_base_quantities" in nomes
    # budget NÃO deve incluir associar_zona_termica (energy only)
    assert "associar_zona_termica" not in nomes
