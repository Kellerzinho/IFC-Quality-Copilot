"""Testes para OllamaClient — cliente HTTP para a API do Ollama."""

from unittest.mock import MagicMock, patch, call
import httpx
import pytest

from src.suggestion_engine.ollama_client import OllamaClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(body: dict, status_code: int = 200) -> MagicMock:
    """Cria um mock de httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = body
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------

def test_generate_success():
    """generate retorna o campo 'response' do JSON em caso de sucesso."""
    client = OllamaClient()
    expected_text = "Sugestão gerada pelo LLM."

    mock_resp = _make_response({"response": expected_text})

    with patch.object(client._client, "post", return_value=mock_resp) as mock_post:
        result = client.generate(prompt="Descreva o espaço.", system="Você é um assistente BIM.")

    assert result == expected_text
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    payload = call_kwargs.kwargs.get("json") or call_kwargs.args[1]
    assert payload["prompt"] == "Descreva o espaço."
    assert payload["system"] == "Você é um assistente BIM."
    assert payload["stream"] is False
    assert payload["model"] == "qwen3.5:9b"


def test_generate_without_system_omits_system_key():
    """generate sem system não inclui a chave 'system' no payload."""
    client = OllamaClient()
    mock_resp = _make_response({"response": "ok"})

    with patch.object(client._client, "post", return_value=mock_resp) as mock_post:
        client.generate(prompt="prompt sem system")
        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs.args[1]
        assert "system" not in payload


def test_generate_retries_on_timeout():
    """generate tenta novamente em caso de TimeoutException e retorna na segunda tentativa."""
    client = OllamaClient()
    mock_resp = _make_response({"response": "sucesso na retry"})

    with patch.object(
        client._client,
        "post",
        side_effect=[httpx.TimeoutException("timeout"), mock_resp],
    ) as mock_post:
        result = client.generate(prompt="teste retry")

    assert result == "sucesso na retry"
    assert mock_post.call_count == 2


def test_generate_uses_backoff_between_retries():
    client = OllamaClient()
    mock_resp = _make_response({"response": "ok"})

    with (
        patch.object(client._client, "post", side_effect=[httpx.TimeoutException("timeout"), mock_resp]) as mock_post,
        patch("src.suggestion_engine.ollama_client.time.sleep") as mock_sleep,
    ):
        result = client.generate(prompt="teste retry")

    assert result == "ok"
    assert mock_post.call_count == 2
    mock_sleep.assert_called_once()


def test_generate_raises_after_retries():
    """generate lança RuntimeError após esgotar todas as tentativas."""
    client = OllamaClient()

    with (
        patch.object(client._client, "post", side_effect=httpx.TimeoutException("timeout")) as mock_post,
        patch("src.suggestion_engine.ollama_client.time.sleep"),
    ):
        with pytest.raises(RuntimeError, match="Ollama indisponivel"):
            client.generate(prompt="falha total")

    # 1 tentativa original + 3 retries = 4 no total
    assert mock_post.call_count == 4


def test_generate_raises_on_connect_error_after_retries():
    """generate lança RuntimeError também para ConnectError após retries."""
    client = OllamaClient()

    with (
        patch.object(client._client, "post", side_effect=httpx.ConnectError("connection refused")),
        patch("src.suggestion_engine.ollama_client.time.sleep"),
    ):
        with pytest.raises(RuntimeError, match="Ollama indisponivel"):
            client.generate(prompt="sem conexão")


# ---------------------------------------------------------------------------
# is_available
# ---------------------------------------------------------------------------

def test_is_available_true():
    """is_available retorna True quando Ollama responde com status 200."""
    client = OllamaClient()
    mock_resp = _make_response({"models": []})

    with patch.object(client._client, "get", return_value=mock_resp):
        assert client.is_available() is True


def test_is_available_false():
    """is_available retorna False quando Ollama não está acessível."""
    client = OllamaClient()

    with patch.object(
        client._client,
        "get",
        side_effect=httpx.ConnectError("connection refused"),
    ):
        assert client.is_available() is False


def test_is_available_false_on_timeout():
    """is_available retorna False em caso de timeout."""
    client = OllamaClient()

    with patch.object(
        client._client,
        "get",
        side_effect=httpx.TimeoutException("timeout"),
    ):
        assert client.is_available() is False


# ---------------------------------------------------------------------------
# list_models
# ---------------------------------------------------------------------------

def test_list_models():
    """list_models retorna lista com os nomes dos modelos disponíveis."""
    client = OllamaClient()
    mock_resp = _make_response({
        "models": [
            {"name": "llama3:8b"},
            {"name": "qwen2.5:7b"},
        ]
    })

    with patch.object(client._client, "get", return_value=mock_resp):
        models = client.list_models()

    assert models == ["llama3:8b", "qwen2.5:7b"]


def test_list_models_empty():
    """list_models retorna lista vazia quando não há modelos instalados."""
    client = OllamaClient()
    mock_resp = _make_response({"models": []})

    with patch.object(client._client, "get", return_value=mock_resp):
        models = client.list_models()

    assert models == []


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------

def test_close_closes_http_client():
    """close() delega ao client HTTP subjacente."""
    client = OllamaClient()

    with patch.object(client._client, "close") as mock_close:
        client.close()

    mock_close.assert_called_once()
