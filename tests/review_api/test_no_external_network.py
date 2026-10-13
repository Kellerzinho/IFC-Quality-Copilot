"""A API sobe em 127.0.0.1 e atende o percurso sem abrir conexão externa.

Sobe um Uvicorn real numa porta livre de loopback, registra toda tentativa de
conexão e de resolução de nome do processo e falha se algum destino não for
loopback.
"""

import http.client
import ipaddress
import json
import socket
import threading
import time
from pathlib import Path
from types import ModuleType

import pytest
import uvicorn

from src.review_api.app import create_app
from src.review_api.local_access import LOOPBACK_HOST


def _is_loopback(host: object) -> bool:
    if host in ("localhost", None):
        return True
    try:
        return ipaddress.ip_address(str(host)).is_loopback
    except ValueError:
        return False


@pytest.fixture
def connection_log(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Recusa e registra qualquer conexão ou DNS fora do loopback."""
    attempts: list[str] = []
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_getaddrinfo = socket.getaddrinfo

    def guarded(original):  # type: ignore[no-untyped-def]
        def connect(self, address):  # type: ignore[no-untyped-def]
            host = address[0] if isinstance(address, tuple) else address
            if not _is_loopback(host):
                attempts.append(f"connect {address}")
                raise OSError("conexão externa bloqueada pelo teste")
            return original(self, address)

        return connect

    def getaddrinfo(host, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not _is_loopback(host):
            attempts.append(f"dns {host}")
            raise OSError("resolução externa bloqueada pelo teste")
        return original_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded(original_connect))
    monkeypatch.setattr(socket.socket, "connect_ex", guarded(original_connect_ex))
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    return attempts


def _request(port: int, method: str, path: str, body: bytes | None = None,
             content_type: str = "application/json") -> tuple[int, dict]:
    conn = http.client.HTTPConnection(LOOPBACK_HOST, port, timeout=120)
    conn.request(method, path, body=body, headers={"Content-Type": content_type})
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, json.loads(data) if data else {}


def test_api_starts_on_loopback_and_answers_without_external_connection(
    tmp_path: Path, corpus_dir: Path, generator: ModuleType, connection_log: list[str]
) -> None:
    config = uvicorn.Config(
        create_app(tmp_path / "data"), host=LOOPBACK_HOST, port=0, log_level="warning"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 30
    while not server.started:
        assert time.monotonic() < deadline, "API não subiu"
        time.sleep(0.05)
    try:
        sockname = server.servers[0].sockets[0].getsockname()
        assert sockname[0] == LOOPBACK_HOST
        port = sockname[1]

        assert _request(port, "GET", "/api/v1/health") == (
            200, {"status": "ok", "schema_version": "m4-plataforma-base/1"}
        )
        status, project = _request(port, "POST", "/api/v1/projects", b'{"name": "rede"}')
        assert status == 201
        model = next(m for m in project["models"] if m["discipline"] == "architecture")
        base = f"/api/v1/projects/{project['project_id']}/models/{model['model_id']}"
        for role, name in (("ifc", generator.ARQ_IFC), ("ids", generator.ARQ_IDS)):
            status, binding = _request(
                port, "PUT", f"{base}/{role}?filename={name}",
                (corpus_dir / name).read_bytes(), "application/octet-stream",
            )
            assert status == 200, binding
        status, _ = _request(port, "POST", f"{base}/confirm", json.dumps({
            "ifc_revision_id": binding["ifc"]["revision_id"],
            "ids_revision_id": binding["ids"]["revision_id"],
        }).encode())
        assert status == 200
        assert _request(port, "GET", f"{base}/elements")[0] == 200
        status, gaps = _request(port, "GET", f"{base}/gaps")
        assert status == 200
        assert gaps["total"] > 0
    finally:
        server.should_exit = True
        thread.join(timeout=30)

    assert connection_log == []
