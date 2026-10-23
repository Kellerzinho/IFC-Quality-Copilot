"""Erros seguros da API de revisão: código, mensagem legível e correlation_id."""

import uuid

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger

from src.review_api.schemas import ApiError


class ApiProblem(Exception):
    """Falha esperada, traduzida para resposta HTTP sem detalhes internos."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        """Guarda status, código estável e mensagem para o usuário."""
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def _respond(status_code: int, code: str, message: str) -> JSONResponse:
    """Monta a resposta ApiError com correlation_id novo."""
    body = ApiError(code=code, message=message, correlation_id=uuid.uuid4().hex)
    return JSONResponse(status_code=status_code, content=body.model_dump())


async def handle_api_problem(_request: Request, exc: Exception) -> JSONResponse:
    """Converte ApiProblem em ApiError."""
    assert isinstance(exc, ApiProblem)
    return _respond(exc.status_code, exc.code, exc.message)


async def handle_validation(_request: Request, exc: Exception) -> JSONResponse:
    """Converte erro de validação de entrada em ApiError 422, sem ecoar o payload."""
    count = len(exc.errors()) if isinstance(exc, RequestValidationError) else 0
    return _respond(422, "entrada_invalida", f"Entrada inválida ({count} problema(s)).")


async def handle_unexpected(_request: Request, exc: Exception) -> JSONResponse:
    """Registra a exceção no log local e responde sem stack trace."""
    response = _respond(500, "erro_interno", "Erro interno. Consulte o log local.")
    logger.exception("Erro não tratado na API de revisão: {}", type(exc).__name__)
    return response
