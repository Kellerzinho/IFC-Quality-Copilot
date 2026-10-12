"""Política de localidade: classificação pelo host literal, sem tocar a rede."""

import pytest
from pydantic import ValidationError

from src.foundation.locality import (
    ExternalEndpointError,
    LocalityPolicy,
    classify_endpoint,
    ensure_local_endpoint,
)


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:11434",
        "http://LOCALHOST.:11434/api/generate",
        "http://127.0.0.1:11434",
        "http://127.8.9.10",
        "http://[::1]:8000",
    ],
)
def test_loopback_endpoints_are_accepted(url: str) -> None:
    assert classify_endpoint(url) == "loopback"
    assert ensure_local_endpoint(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "https://api.bsdd.buildingsmart.org",
        "https://api.openai.com/v1",
        "http://10.0.0.5:11434",
        "http://ollama.ime.eb.br:11434",
    ],
)
def test_external_endpoints_are_refused_without_policy(url: str) -> None:
    assert classify_endpoint(url) == "external"
    with pytest.raises(ExternalEndpointError):
        ensure_local_endpoint(url)


def test_declared_internal_host_and_network_are_accepted() -> None:
    policy = LocalityPolicy(internal_hosts=["Ollama.IME.eb.br."], internal_networks=["10.0.0.0/8"])

    assert classify_endpoint("http://ollama.ime.eb.br:11434", policy) == "internal"
    assert classify_endpoint("http://10.1.2.3:11434", policy) == "internal"
    assert classify_endpoint("http://11.0.0.1", policy) == "external"


@pytest.mark.parametrize(
    "url",
    ["http://ime.eb.br.evil.example", "http://evil-ime.eb.br", "http://sub.ime.eb.br"],
)
def test_internal_host_match_is_exact(url: str) -> None:
    policy = LocalityPolicy(internal_hosts=["ime.eb.br"])

    assert classify_endpoint(url, policy) == "external"


def test_invalid_internal_network_is_rejected_at_policy_creation() -> None:
    with pytest.raises(ValidationError):
        LocalityPolicy(internal_networks=["10.0.0.0/33"])


@pytest.mark.parametrize("url", ["localhost:11434", "", "http://"])
def test_url_without_scheme_or_host_is_an_error(url: str) -> None:
    with pytest.raises(ValueError, match="sem"):
        classify_endpoint(url)


def test_refusal_message_does_not_leak_credentials() -> None:
    with pytest.raises(ExternalEndpointError) as excinfo:
        ensure_local_endpoint("https://usuario:segredo@api.example.com/v1")

    assert "segredo" not in str(excinfo.value)
    assert "usuario" not in str(excinfo.value)
