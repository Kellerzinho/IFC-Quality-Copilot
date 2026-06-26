"""Servidor MCP HTTP/Streamable para conectores remotos (ex: ChatGPT)."""

from __future__ import annotations

import contextlib
import os
from collections.abc import AsyncIterator

import uvicorn
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route

from src.mcp_server.server import server


def _expected_bearer_token() -> str | None:
    token = os.getenv("IFC_COPILOT_MCP_TOKEN") or os.getenv("MCP_BEARER_TOKEN")
    return token.strip() if token and token.strip() else None


def _is_authorized(request: Request) -> bool:
    expected = _expected_bearer_token()
    if expected is None:
        return True
    auth = request.headers.get("authorization", "")
    scheme, _, token = auth.partition(" ")
    return scheme.lower() == "bearer" and token == expected


def create_app() -> Starlette:
    """Cria app ASGI com endpoint MCP em /mcp."""
    session_manager = StreamableHTTPSessionManager(
        app=server,
        json_response=True,
        stateless=False,
    )

    class MCPASGIApp:
        async def __call__(self, scope, receive, send) -> None:
            request = Request(scope, receive=receive)
            if not _is_authorized(request):
                response = JSONResponse({"error": "unauthorized"}, status_code=401)
                await response(scope, receive, send)
                return
            await session_manager.handle_request(scope, receive, send)

    async def health(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "server": "ifc-quality-copilot"})

    @contextlib.asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncIterator[None]:
        async with session_manager.run():
            yield

    middleware = [
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
            allow_headers=["*"],
        )
    ]
    return Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            Mount("/mcp", app=MCPASGIApp()),
            Mount("/", app=Starlette(routes=[Route("/", health, methods=["GET"])])),
        ],
        middleware=middleware,
        lifespan=lifespan,
    )


def main() -> None:
    """Executa o servidor HTTP local/remoto."""
    host = os.getenv("IFC_COPILOT_MCP_HOST", "0.0.0.0")
    port = int(os.getenv("IFC_COPILOT_MCP_PORT", "8765"))
    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":
    main()
