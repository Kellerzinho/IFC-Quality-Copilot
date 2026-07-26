"""Cliente HTTP para a API do Ollama."""

from __future__ import annotations

import json
import time

import httpx
from loguru import logger

from src.config import get_settings


class OllamaClient:
    """Cliente HTTP para API do Ollama."""

    _RETRY_EXCEPTIONS = (httpx.TimeoutException, httpx.ConnectError)

    _MIN_NUM_CTX = 2048
    """Piso da janela de contexto. Abaixo disso nao ha ganho de velocidade."""

    _CHARS_PER_TOKEN = 3.0
    """Estimativa conservadora para pt-BR (o real fica entre 3,5 e 4,5)."""

    @classmethod
    def _fit_num_ctx(cls, prompt: str, system: str | None, num_predict: int, ceiling: int) -> int:
        """Dimensiona a janela de contexto ao prompt real, em potencias de 2.

        Uma janela de 8192 para um prompt de ~460 tokens desperdiça KV cache e
        atrasa a geracao: medido com o modelo 100% na GPU, cair para 2048 acelera
        gemma2:9b em 30% e qwen2.5:7b em 14%, sem alterar a resposta. A janela
        nunca fica menor que prompt + resposta — truncar cortaria o fim do
        prompt, onde esta o contrato de saida.
        """
        chars = len(prompt) + len(system or "")
        estimado = int(chars / cls._CHARS_PER_TOKEN) + num_predict
        necessario = int(estimado * 1.25)  # margem para erro da estimativa

        janela = cls._MIN_NUM_CTX
        while janela < necessario and janela < ceiling:
            janela *= 2
        return min(janela, ceiling)

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
    ) -> tuple[str, dict]:
        """Gera resposta do LLM via POST /api/generate com retry e backoff.

        Retorna (response_text, ollama_metrics) onde ollama_metrics contem:
        total_duration, load_duration, prompt_eval_duration, eval_duration,
        prompt_eval_count, eval_count (todos em nanossegundos quando duration).
        """
        settings = get_settings()
        options: dict = {
            "temperature": temperature if temperature is not None else settings.ollama_temperature,
            "num_ctx": self._fit_num_ctx(
                prompt,
                system,
                settings.ollama_num_predict,
                settings.ollama_num_ctx,
            ),
            "num_predict": settings.ollama_num_predict,
            "repeat_penalty": settings.ollama_repeat_penalty,
            "top_p": settings.ollama_top_p,
        }
        if settings.ollama_seed is not None:
            options["seed"] = settings.ollama_seed

        url = f"{self.base_url}/api/generate"
        last_exc: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                response_text, metrics = self._post_generate(
                    url=url,
                    prompt=prompt,
                    system=system,
                    options=options,
                    think_enabled=settings.ollama_think,
                    json_format=True,
                )
                if response_text.strip():
                    return response_text, metrics

                if settings.ollama_think:
                    logger.warning(
                        "Ollama retornou resposta vazia com think=True; tentando novamente sem think"
                    )
                    return self._post_generate(
                        url=url,
                        prompt=prompt,
                        system=system,
                        options=options,
                        think_enabled=False,
                        json_format=True,
                    )

                logger.warning(
                    "Ollama retornou resposta vazia em modo JSON; tentando novamente sem format=json"
                )
                return self._post_generate(
                    url=url,
                    prompt=prompt,
                    system=system,
                    options=options,
                    think_enabled=False,
                    json_format=False,
                )
            except self._RETRY_EXCEPTIONS as exc:
                last_exc = exc
                logger.warning(
                    "Tentativa {}/{} no Ollama falhou (timeout/conexao, timeout={}s, model={}): {}",
                    attempt + 1,
                    self._max_retries + 1,
                    self._timeout_seconds,
                    self.model,
                    exc,
                )
                if attempt >= self._max_retries:
                    break
                backoff = self._retry_backoff_seconds * (2 ** attempt)
                if backoff > 0:
                    time.sleep(backoff)
            except httpx.HTTPStatusError as exc:
                logger.error("Erro HTTP do Ollama (sem retry): {}", exc)
                raise RuntimeError(f"Ollama HTTP error: {exc}") from exc

        raise RuntimeError(
            f"Ollama indisponivel apos {self._max_retries + 1} tentativas: {last_exc}"
        )

    def _post_generate(
        self,
        *,
        url: str,
        prompt: str,
        system: str | None,
        options: dict,
        think_enabled: bool,
        json_format: bool,
    ) -> tuple[str, dict]:
        settings = get_settings()
        payload: dict = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "think": think_enabled,
            "keep_alive": settings.ollama_keep_alive,
            "options": options,
        }
        if json_format:
            payload["format"] = "json"
        if system is not None:
            payload["system"] = system

        response = self._client.post(url, json=payload)
        response.raise_for_status()
        body = response.json()
        if "response" not in body:
            raise RuntimeError("Resposta do Ollama sem campo 'response'")
        metrics = {
            "total_duration": body.get("total_duration", 0),
            "load_duration": body.get("load_duration", 0),
            "prompt_eval_duration": body.get("prompt_eval_duration", 0),
            "eval_duration": body.get("eval_duration", 0),
            "prompt_eval_count": body.get("prompt_eval_count", 0),
            "eval_count": body.get("eval_count", 0),
        }
        return self._extract_response_text(body), metrics

    def _extract_response_text(self, body: dict) -> str:
        response_text = str(body.get("response") or "")
        if response_text.strip():
            return response_text

        thinking = body.get("thinking")
        if thinking is None:
            return response_text

        if isinstance(thinking, str):
            thinking_text = thinking
        else:
            thinking_text = json.dumps(thinking, ensure_ascii=False)

        if thinking_text.strip():
            logger.warning(
                "Ollama retornou response vazia mas thinking preenchido; usando thinking como saida"
            )
            return thinking_text
        return response_text

    def warm_up(self) -> bool:
        """Aquece o modelo enviando keep_alive sem prompt real.

        Retorna True se o aquecimento foi bem-sucedido. Util para garantir
        que o modelo permaneca carregado antes de iniciar um batch.
        """
        settings = get_settings()
        try:
            response = self._client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": "",
                    "stream": False,
                    "keep_alive": settings.ollama_keep_alive,
                },
            )
            response.raise_for_status()
            logger.debug("Ollama warm_up: modelo {} aquecido", self.model)
            return True
        except Exception as exc:
            logger.debug("Ollama warm_up falhou: {}", exc)
            return False

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
