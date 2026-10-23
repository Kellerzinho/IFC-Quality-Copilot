"""Composição da API local de revisão M4 (FastAPI, somente loopback)."""

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from pydantic import TypeAdapter

from src.review_api.errors import (
    ApiProblem,
    handle_api_problem,
    handle_unexpected,
    handle_validation,
)
from src.review_api.local_access import make_local_guard
from src.review_api.registry import ProjectRegistry
from src.review_api.routes import analysis, projects
from src.review_api.schemas import SCHEMA_VERSION, Health, Suggestion

DEFAULT_PORT = 8765


def default_data_root() -> Path:
    """Raiz de dados fora do código (M6): %LOCALAPPDATA% ou ~/.local/share."""
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "IFC-Quality-Copilot" / "m4-dev"


def _openapi_with_contracts(app: FastAPI) -> dict[str, Any]:
    """Gera o OpenAPI e acrescenta contratos ainda sem rota (Suggestion)."""
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        separate_input_output_schemas=False,
    )
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    suggestion = TypeAdapter(Suggestion).json_schema(
        ref_template="#/components/schemas/{model}"
    )
    components.update(suggestion.pop("$defs", {}))
    discriminator = suggestion.get("discriminator", {})
    if "mapping" in discriminator:
        discriminator["mapping"] = dict(sorted(discriminator["mapping"].items()))
    components["Suggestion"] = suggestion
    schema["components"]["schemas"] = dict(sorted(components.items()))
    app.openapi_schema = schema
    return schema


def create_app(data_root: Path | None = None, port: int = DEFAULT_PORT) -> FastAPI:
    """Cria a aplicação com registro em memória e proteções de acesso local.

    Args:
        data_root: diretório dos blobs; padrão fora do repositório.
        port: porta da API, usada na allowlist de Origin.
    """
    app = FastAPI(
        title="IFC Quality Copilot — API de revisão (M4)",
        version=SCHEMA_VERSION,
        description=(
            "API local (127.0.0.1) da fatia plataforma-base. Lacuna e Sugestão são "
            "PROVISÓRIAS (aguardando M2/M3)."
        ),
        openapi_url="/api/v1/openapi.json",
        docs_url=None,
        redoc_url=None,
        swagger_ui_oauth2_redirect_url=None,
    )
    app.state.registry = ProjectRegistry(data_root or default_data_root())
    app.middleware("http")(make_local_guard(port))
    app.add_exception_handler(ApiProblem, handle_api_problem)
    app.add_exception_handler(RequestValidationError, handle_validation)
    app.add_exception_handler(Exception, handle_unexpected)
    app.include_router(projects.router)
    app.include_router(analysis.router)

    @app.get("/api/v1/health", response_model=Health, operation_id="getHealth", tags=["sistema"])
    def health() -> Health:
        """Indica que a API local está respondendo."""
        return Health()

    app.openapi = lambda: _openapi_with_contracts(app)
    return app
