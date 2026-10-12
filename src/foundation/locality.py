"""Política de localidade da plataforma.

Toda inferência e todo dado da plataforma ficam na máquina local ou na rede
interna do IME. Não há fallback para APIs externas: um endpoint fora da
política é recusado com erro explícito, nunca trocado em silêncio por outro.
A classificação usa o host literal da URL e não resolve DNS (não toca a rede).
"""

from ipaddress import ip_address, ip_network
from typing import Literal
from urllib.parse import urlsplit

from loguru import logger
from pydantic import BaseModel, Field, field_validator

EndpointScope = Literal["loopback", "internal", "external"]


class ExternalEndpointError(ValueError):
    """Endpoint fora da política de localidade; não existe fallback externo."""


class LocalityPolicy(BaseModel):
    """Hosts e redes internos aceitos além do loopback, que é sempre aceito."""

    internal_hosts: list[str] = Field(
        default_factory=list,
        description="Nomes de host internos do IME, comparados por igualdade exata",
    )
    internal_networks: list[str] = Field(
        default_factory=list,
        description="Redes internas do IME em notação CIDR",
    )

    @field_validator("internal_hosts")
    @classmethod
    def _normalize_hosts(cls, hosts: list[str]) -> list[str]:
        """Normaliza para minúsculas e remove o ponto final de FQDN."""
        return [host.strip().lower().rstrip(".") for host in hosts if host.strip()]

    @field_validator("internal_networks")
    @classmethod
    def _validate_networks(cls, networks: list[str]) -> list[str]:
        """Rejeita CIDR inválido já na construção da política."""
        for network in networks:
            ip_network(network, strict=False)
        return networks


def _host_of(url: str) -> str:
    """Extrai o host normalizado; credenciais e porta nunca entram no resultado."""
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        raise ValueError(f"URL sem esquema ou host: {url!r}")
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        raise ValueError(f"URL sem host: {url!r}")
    return host


def classify_endpoint(url: str, policy: LocalityPolicy | None = None) -> EndpointScope:
    """Classifica o endpoint como loopback, interno (pela política) ou externo."""
    active = policy or LocalityPolicy()
    host = _host_of(url)
    if host == "localhost":
        return "loopback"
    try:
        address = ip_address(host)
    except ValueError:
        return "internal" if host in active.internal_hosts else "external"
    if address.is_loopback:
        return "loopback"
    if any(address in ip_network(net, strict=False) for net in active.internal_networks):
        return "internal"
    return "external"


def ensure_local_endpoint(url: str, policy: LocalityPolicy | None = None) -> str:
    """Devolve a URL se ela for local ou interna; caso contrário, recusa sem fallback."""
    if classify_endpoint(url, policy) == "external":
        host = _host_of(url)
        logger.warning("Endpoint externo recusado pela política de localidade: {}", host)
        raise ExternalEndpointError(f"Endpoint externo não permitido (sem fallback): {host}")
    return url
