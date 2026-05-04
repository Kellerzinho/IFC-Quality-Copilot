"""Cliente HTTP para a API do Ollama."""

from __future__ import annotations

import time

import httpx
from loguru import logger

from src.config import get_settings


class OllamaClient:
    """Cliente HTTP para API do Ollama."""

    _RETRY_EXCEPTIONS = (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError)

    def __init__(self, base_url: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self.base_url = base_url or settings.ollama_url
        self.model = model or settings.ollama_model
        self._timeout_seconds = settings.ollama_generate_timeout_seconds
        self._max_retries = max(0, settings.ollama_max_retries)
        self._retry_backoff_seconds = max(0.0, settings.ollama_retry_backoff_seconds)
        self._client = httpx.Client(timeout=self._timeout_seconds)

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float | None = None,
    ) -> str:
        """Gera resposta do LLM via POST /api/generate com retry e backoff."""
        settings = get_settings()
        payload: dict = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "think": settings.ollama_think,
            "keep_alive": settings.ollama_keep_alive,
            "options": {
                "temperature": temperature if temperature is not None else settings.ollama_temperature,
                "num_ctx": settings.ollama_num_ctx,
                "num_predict": settings.ollama_num_predict,
                "repeat_penalty": 1.1,
                "top_p": 0.9,
            },
        }
        if system is not None:
            payload["system"] = system

        url = f"{self.base_url}/api/generate"
        last_exc: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.post(url, json=payload)
                response.raise_for_status()
                body = response.json()
                if "response" not in body:
                    raise RuntimeError("Resposta do Ollama sem campo 'response'")
                return body["response"]
            except self._RETRY_EXCEPTIONS as exc:
                last_exc = exc
                logger.warning(
                    "Tentativa {}/{} no Ollama falhou: {}",
                    attempt + 1,
                    self._max_retries + 1,
                    exc,
                )
                if attempt >= self._max_retries:
                    break
                backoff = self._retry_backoff_seconds * (2 ** attempt)
                if backoff > 0:
                    time.sleep(backoff)

        raise RuntimeError(
            f"Ollama indisponivel apos {self._max_retries + 1} tentativas: {last_exc}"
        )

    def is_available(self) -> bool:
        """Verifica se o Ollama esta rodando via GET /api/tags."""
        try:
            response = self._client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            return True
        except Exception as exc:
            logger.debug("Ollama nao disponivel: {}", exc)
            return False

    def list_models(self) -> list[str]:
        """Lista os nomes dos modelos instalados no Ollama."""
        try:
            response = self._client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            return [m["name"] for m in response.json().get("models", [])]
        except Exception as exc:
            logger.warning("Nao foi possivel listar modelos Ollama: {}", exc)
            return []

    def close(self) -> None:
        """Fecha o cliente HTTP."""
        self._client.close()
