"""Listagem e reabertura de projetos do armazenamento local (abrir projeto existente)."""

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType

import pytest
from fastapi.testclient import TestClient

from src.review_api import registry as registry_module
from src.review_api.app import create_app
from src.review_api.project_store import DB_FILENAME
from tests.review_api.conftest import load_pair, upload

BASE_URL = "http://127.0.0.1:8765"


def _client(data_root: Path) -> TestClient:
    return TestClient(create_app(data_root), base_url=BASE_URL)


def _list(client: TestClient) -> dict:
    resp = client.get("/api/v1/projects")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == len(body["items"])
    return body


class _Relogio:
    """Relógio controlado: cada leitura avança um minuto."""

    def __init__(self) -> None:
        self.agora = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.agora += timedelta(minutes=1)
        return self.agora


@pytest.fixture
def relogio(monkeypatch: pytest.MonkeyPatch) -> _Relogio:
    """Substitui o relógio do registro por um determinístico."""
    clock = _Relogio()
    monkeypatch.setattr(registry_module, "utc_now", clock)
    return clock


def test_empty_storage_lists_no_projects(client: TestClient) -> None:
    body = _list(client)
    assert body["total"] == 0
    assert body["schema_version"] == "m4-plataforma-base/1"


def test_listing_brings_models_with_revisions(
    client: TestClient, corpus_dir: Path, generator: ModuleType
) -> None:
    pair = load_pair(client, corpus_dir, generator)
    [item] = _list(client)["items"]
    assert item["project_id"] == pair.project_id
    assert item["name"] == "M4 sintético"
    by_discipline = {m["discipline"]: m for m in item["models"]}
    assert set(by_discipline) == {"architecture", "structure"}
    arq = by_discipline["architecture"]
    assert arq["model_id"] == pair.architecture
    assert arq["ifc"]["display_name"] == generator.ARQ_IFC
    assert len(arq["ifc"]["revision_id"]) == 64
    assert arq["confirmed"] is True
    assert datetime.fromisoformat(item["created_at"]) <= datetime.fromisoformat(item["updated_at"])


def test_most_recently_updated_comes_first(
    client: TestClient, relogio: _Relogio, corpus_dir: Path, generator: ModuleType
) -> None:
    first = client.post("/api/v1/projects", json={"name": "Primeiro"}).json()
    client.post("/api/v1/projects", json={"name": "Segundo"})
    assert [i["name"] for i in _list(client)["items"]] == ["Segundo", "Primeiro"]

    model_id = first["models"][0]["model_id"]
    upload(
        client,
        f"/api/v1/projects/{first['project_id']}/models/{model_id}",
        "ifc",
        corpus_dir / generator.ARQ_IFC,
    )
    items = _list(client)["items"]
    assert [i["name"] for i in items] == ["Primeiro", "Segundo"]
    assert items[0]["created_at"] < items[0]["updated_at"]


def test_projects_survive_api_restart(
    tmp_path: Path, corpus_dir: Path, generator: ModuleType
) -> None:
    """Reiniciar a API mantém projeto, revisões, confirmação e acesso aos elementos."""
    data_root = tmp_path / "data"
    pair = load_pair(_client(data_root), corpus_dir, generator)

    again = _client(data_root)
    [item] = _list(again)["items"]
    assert item["project_id"] == pair.project_id
    project = again.get(f"/api/v1/projects/{pair.project_id}")
    assert project.status_code == 200
    assert all(m["confirmed"] for m in project.json()["models"])
    elements = again.get(f"{pair.base(pair.architecture)}/elements")
    assert elements.status_code == 200
    assert elements.json()["total"] > 0


def test_corrupted_row_is_skipped_not_fatal(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    _client(data_root).post("/api/v1/projects", json={"name": "Íntegro"})
    with sqlite3.connect(data_root / DB_FILENAME) as conn:
        conn.execute(
            "INSERT INTO projects VALUES ('x', 'Quebrado', '2026-01-01T00:00:00+00:00', "
            "'2026-01-01T00:00:00+00:00', '{nao json')"
        )
    assert [i["name"] for i in _list(_client(data_root))["items"]] == ["Íntegro"]


def test_name_with_markup_is_listed_as_literal_text(client: TestClient) -> None:
    client.post("/api/v1/projects", json={"name": "<b>Obra</b>"})
    assert _list(client)["items"][0]["name"] == "<b>Obra</b>"


@pytest.mark.parametrize(
    "headers",
    [
        {"host": "evil.example"},
        {"origin": "http://evil.example"},
        {"origin": "null"},
        {"origin": "http://localhost:5173"},
    ],
)
def test_listing_follows_local_access_rules(client: TestClient, headers: dict) -> None:
    client.post("/api/v1/projects", json={"name": "Sigiloso"})
    resp = client.get("/api/v1/projects", headers=headers)
    assert resp.status_code == 403
    assert "Sigiloso" not in resp.text


def test_listing_is_allowed_from_dev_ui_origin(client: TestClient) -> None:
    resp = client.get("/api/v1/projects", headers={"origin": "http://127.0.0.1:5173"})
    assert resp.status_code == 200
    assert "access-control-allow-origin" not in resp.headers
