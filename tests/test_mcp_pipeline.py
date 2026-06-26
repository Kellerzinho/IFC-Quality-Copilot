"""Testes das tools MCP integradas ao QualityPipeline."""

import asyncio
import json

from starlette.testclient import TestClient

from src.models import Suggestion, SuggestionMetrics, SuggestionSet


def _parse(result) -> dict:
    return json.loads(result[0].text)


def _fake_pipeline_generate(self, issue, building_context, **kwargs):
    """SuggestionGenerator.generate falso para testes MCP sem Ollama."""
    prop = issue.context.get("check_property")
    if issue.issue_type == "space_unnamed":
        value = "Sala de Estar"
    elif prop == "ThermalTransmittance":
        value = 2.48
    elif prop == "FireRating":
        value = "EI 30"
    elif prop == "IsExternal":
        value = True
    elif prop == "Category":
        value = "LIVING"
    else:
        value = "Valor Teste"

    return SuggestionSet(
        issue_id=issue.id,
        suggestions=[
            Suggestion(
                label=str(value),
                value=value,
                justification="sugestao fake para teste MCP",
                confidence="alta",
                source="llm",
            )
        ],
        metrics=SuggestionMetrics(issue_id=issue.id),
    )


def _wait_pipeline_worker(session, timeout: float = 5.0) -> None:
    pipeline = session["pipeline"]
    if pipeline.worker and pipeline.worker._thread:
        pipeline.worker._thread.join(timeout=timeout)


def test_tool_pipeline_flow_lists_suggestions_and_applies(tmp_path, complete_test_model, monkeypatch):
    """Fluxo MCP integrado: iniciar pipeline, listar sugestoes e aplicar com aprovacao."""
    from src.mcp_server.tools_pipeline import (
        handle_aplicar_sugestao,
        handle_fechar_pipeline,
        handle_iniciar_pipeline,
        handle_listar_sugestoes,
        handle_progresso_sugestoes,
    )

    monkeypatch.setattr(
        "src.suggestion_engine.suggestion.SuggestionGenerator.generate",
        _fake_pipeline_generate,
    )
    monkeypatch.setattr(
        "src.bsdd.context_builder.BSDDContextBuilder.build",
        lambda self, issue, ids_context=None: None,
    )

    ifc_file, _ = complete_test_model
    ifc_path = str(tmp_path / "test_model.ifc")
    ifc_file.write(ifc_path)
    session = {"pipeline": None, "analyzer": None, "writer": None, "audit_logger": None}

    result = asyncio.run(handle_iniciar_pipeline(session, {"filepath": ifc_path}))
    data = _parse(result)
    assert data["sucesso"] is True
    assert data["total_issues"] > 0
    assert session["pipeline"] is not None

    _wait_pipeline_worker(session)

    progress = _parse(asyncio.run(handle_progresso_sugestoes(session, {})))
    assert progress["sucesso"] is True
    assert progress["progresso"]["queued"] == 0

    suggestions = _parse(asyncio.run(handle_listar_sugestoes(session, {})))
    assert suggestions["sucesso"] is True
    assert suggestions["total"] > 0
    issue_id = suggestions["items"][0]["issue"]["issue_id"]

    applied = _parse(asyncio.run(handle_aplicar_sugestao(
        session,
        {"issue_id": issue_id, "suggestion_index": 0, "aprovado_pelo_usuario": True},
    )))
    assert applied["sucesso"] is True
    assert applied["post_validacao"] is not None

    asyncio.run(handle_fechar_pipeline(session, {}))


def test_tool_aplicar_sugestao_requires_approval(tmp_path, complete_test_model, monkeypatch):
    """aplicar_sugestao exige aprovado_pelo_usuario=true."""
    from src.mcp_server.tools_pipeline import (
        handle_aplicar_sugestao,
        handle_fechar_pipeline,
        handle_iniciar_pipeline,
        handle_listar_issues,
    )

    monkeypatch.setattr(
        "src.suggestion_engine.suggestion.SuggestionGenerator.generate",
        _fake_pipeline_generate,
    )
    monkeypatch.setattr(
        "src.bsdd.context_builder.BSDDContextBuilder.build",
        lambda self, issue, ids_context=None: None,
    )

    ifc_file, _ = complete_test_model
    ifc_path = str(tmp_path / "test_model.ifc")
    ifc_file.write(ifc_path)
    session = {"pipeline": None, "analyzer": None, "writer": None, "audit_logger": None}
    _parse(asyncio.run(handle_iniciar_pipeline(session, {"filepath": ifc_path})))
    issues = _parse(asyncio.run(handle_listar_issues(session, {"limit": 1})))
    issue_id = issues["issues"][0]["issue_id"]

    result = _parse(asyncio.run(handle_aplicar_sugestao(session, {"issue_id": issue_id})))

    assert result["sucesso"] is False
    assert "aprova" in result["erro"].lower()
    asyncio.run(handle_fechar_pipeline(session, {}))


def test_http_app_health():
    """Servidor HTTP para conectores remotos expoe health check."""
    from src.mcp_server.http_server import create_app

    with TestClient(create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["server"] == "ifc-quality-copilot"
