"""Proteções de acesso local (M6 §13.1) — versão mínima desta fatia.

- bind somente em 127.0.0.1 (imposto em ``__main__``);
- Host precisa ser 127.0.0.1 ou localhost;
- Origin, quando presente, precisa estar na allowlist exata: a própria API e,
  para o Vite de desenvolvimento (proxy /api), apenas http://127.0.0.1:5173;
  ``null`` é recusado; sem CORS ``*``.

PROVISÓRIO: o nonce de instância para comandos fica para M6.
"""

from collections.abc import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.review_api.schemas import ApiError

LOOPBACK_HOST = "127.0.0.1"
ALLOWED_HOSTNAMES = frozenset({"127.0.0.1", "localhost"})
DEV_UI_PORT = 5173


DEV_UI_ORIGIN = f"http://{LOOPBACK_HOST}:{DEV_UI_PORT}"


def allowed_origins(api_port: int) -> frozenset[str]:
    """Origens exatas aceitas: a própria API e, em dev, só http://127.0.0.1:5173."""
    origins = {f"http://{host}:{api_port}" for host in ALLOWED_HOSTNAMES}
    origins.add(DEV_UI_ORIGIN)
    return frozenset(origins)


def _hostname(host_header: str) -> str:
    """Extrai o nome do cabeçalho Host (sem porta)."""
    if host_header.startswith("["):
        return host_header.split("]")[0] + "]"
    return host_header.rsplit(":", 1)[0] if ":" in host_header else host_header


def _reject(code: str, message: str) -> JSONResponse:
    """Resposta 403 no formato ApiError."""
    body = ApiError(code=code, message=message, correlation_id="acesso-local")
    return JSONResponse(status_code=403, content=body.model_dump())


def make_local_guard(
    api_port: int,
) -> Callable[[Request, Callable[[Request], Awaitable[Response]]], Awaitable[Response]]:
    """Cria o middleware que recusa Host e Origin fora da allowlist."""
    origins = allowed_origins(api_port)

    async def guard(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if _hostname(request.headers.get("host", "")) not in ALLOWED_HOSTNAMES:
            return _reject("host_recusado", "Host não permitido para a API local.")
        origin = request.headers.get("origin")
        if origin is not None and origin not in origins:
            return _reject("origem_recusada", "Origem não permitida para a API local.")
        return await call_next(request)

    return guard
