"""Testes para OllamaClient — cliente HTTP para a API do Ollama."""

from unittest.mock import MagicMock, patch, call
import httpx
import pytest

from src.config import get_settings
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

    assert isinstance(result, tuple)
    text, metrics = result
    assert text == expected_text
    assert isinstance(metrics, dict)
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


def test_generate_sends_think_false_by_default():
    """generate envia think=false por padrao para evitar saida no campo thinking."""
    client = OllamaClient()
    mock_resp = _make_response({"response": "ok"})

    with patch.object(client._client, "post", return_value=mock_resp) as mock_post:
        text, _ = client.generate(prompt="teste")

    assert text == "ok"
    payload = mock_post.call_args.kwargs["json"]
    assert payload["think"] is False


def test_generate_uses_thinking_field_when_response_is_empty():
    """generate aproveita thinking quando Ollama coloca a saida JSON nesse campo."""
    client = OllamaClient()
    mock_resp = _make_response(
        {
            "response": "",
            "thinking": '{"opcoes":[{"valor":"ok","justificativa":"teste","confianca":"alta"}]}',
        }
    )

    with patch.object(client._client, "post", return_value=mock_resp):
        text, _ = client.generate(prompt="teste")

    assert text == '{"opcoes":[{"valor":"ok","justificativa":"teste","confianca":"alta"}]}'


def test_generate_retries_without_think_when_response_is_empty_and_think_is_enabled():
    """generate tenta novamente sem think quando Ollama devolve response vazia."""
    client = OllamaClient()
    empty_resp = _make_response({"response": ""})
    fallback_resp = _make_response({"response": '{"suggestions": []}'})

    with (
        patch("src.suggestion_engine.ollama_client.get_settings") as mock_settings,
        patch.object(client._client, "post", side_effect=[empty_resp, fallback_resp]) as mock_post,
    ):
        settings = mock_settings.return_value
        settings.ollama_temperature = 0.1
        settings.ollama_num_ctx = 8192
        settings.ollama_num_predict = 1024
        settings.ollama_repeat_penalty = 1.1
        settings.ollama_top_p = 0.9
        settings.ollama_seed = 42
        settings.ollama_think = True
        settings.ollama_keep_alive = "15m"
        text, _ = client.generate(prompt="teste")

    assert text == '{"suggestions": []}'
    assert mock_post.call_count == 2
    first_payload = mock_post.call_args_list[0].kwargs["json"]
    second_payload = mock_post.call_args_list[1].kwargs["json"]
    assert first_payload["think"] is True
    assert second_payload["think"] is False


def test_generate_retries_without_json_format_when_response_is_empty():
    """generate tenta modo texto quando Ollama devolve response vazia em format=json."""
    client = OllamaClient()
    empty_resp = _make_response({"response": ""})
    fallback_resp = _make_response({"response": '{"suggestions": []}'})

    with patch.object(client._client, "post", side_effect=[empty_resp, fallback_resp]) as mock_post:
        text, _ = client.generate(prompt="teste")

    assert text == '{"suggestions": []}'
    assert mock_post.call_count == 2
    first_payload = mock_post.call_args_list[0].kwargs["json"]
    second_payload = mock_post.call_args_list[1].kwargs["json"]
    assert first_payload["format"] == "json"
    assert "format" not in second_payload


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

    text, _ = result
    assert text == "sucesso na retry"
    assert mock_post.call_count == 2


def test_generate_uses_backoff_between_retries():
    client = OllamaClient()
    mock_resp = _make_response({"response": "ok"})

    with (
        patch.object(client._client, "post", side_effect=[httpx.TimeoutException("timeout"), mock_resp]) as mock_post,
        patch("src.suggestion_engine.ollama_client.time.sleep") as mock_sleep,
    ):
        result = client.generate(prompt="teste retry")

    text, _ = result
    assert text == "ok"
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


# ---------------------------------------------------------------------------
# num_ctx adaptativo
# ---------------------------------------------------------------------------


def test_num_ctx_shrinks_for_short_prompts(monkeypatch):
    """Prompt curto não paga o custo de uma janela de contexto de 8192.

    Medido: com o modelo 100% na GPU, cair de num_ctx 8192 para 2048 acelera
    gemma2:9b em 30% e qwen2.5:7b em 14%, sem mudar a resposta. Os prompts do
    projeto têm mediana ~464 tokens.
    """
    client = OllamaClient()
    captured: dict = {}

    def fake_post(url, json=None, **kwargs):
        captured["options"] = json["options"]
        return _make_response({"response": '{"opcoes": []}'})

    monkeypatch.setattr(client._client, "post", fake_post)

    client.generate(prompt="issue_id: abc\ntipo: pset_missing", system="sys")

    assert captured["options"]["num_ctx"] == 2048


def test_num_ctx_grows_to_fit_long_prompts(monkeypatch):
    """Prompt longo nunca é truncado: a janela cresce para caber prompt + resposta.

    Truncar o prompt cortaria justamente o fim, onde está o contrato de saída.
    """
    client = OllamaClient()
    captured: dict = {}

    def fake_post(url, json=None, **kwargs):
        captured["options"] = json["options"]
        return _make_response({"response": '{"opcoes": []}'})

    monkeypatch.setattr(client._client, "post", fake_post)

    # ~6000 tokens de prompt: acima de qualquer janela pequena
    client.generate(prompt="palavra " * 6000, system="sys")

    opts = captured["options"]
    assert opts["num_ctx"] >= 8192


def test_num_ctx_never_exceeds_configured_ceiling(monkeypatch):
    """O teto configurado em ollama_num_ctx continua sendo respeitado."""
    client = OllamaClient()
    captured: dict = {}

    def fake_post(url, json=None, **kwargs):
        captured["options"] = json["options"]
        return _make_response({"response": '{"opcoes": []}'})

    monkeypatch.setattr(client._client, "post", fake_post)

    client.generate(prompt="palavra " * 100_000, system="sys")

    assert captured["options"]["num_ctx"] <= get_settings().ollama_num_ctx
