"""Fixtures da API de revisão M4: corpus sintético e cliente em loopback."""

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import pytest
from fastapi.testclient import TestClient

from src.review_api.app import create_app

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR_PATH = REPO_ROOT / "scripts" / "m4_gerar_corpus_sintetico.py"
OCTET = {"Content-Type": "application/octet-stream"}


def load_generator() -> ModuleType:
    """Importa o script gerador do corpus (fora do pacote src)."""
    spec = importlib.util.spec_from_file_location("m4_corpus", GENERATOR_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def generator() -> ModuleType:
    """Módulo do gerador de corpus."""
    return load_generator()


@pytest.fixture(scope="session")
def corpus_dir(tmp_path_factory: pytest.TempPathFactory, generator: ModuleType) -> Path:
    """Gera o corpus sintético uma vez por sessão, em diretório temporário."""
    out = tmp_path_factory.mktemp("m4_corpus")
    generator.generate(out)
    return out


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    """Cliente com Host 127.0.0.1 e dados em diretório temporário."""
    return TestClient(create_app(tmp_path / "data"), base_url="http://127.0.0.1:8765")


@dataclass
class Pair:
    """Projeto com as duas linhas carregadas."""

    project_id: str
    architecture: str
    structure: str

    def base(self, model_id: str) -> str:
        """Prefixo das rotas de uma linha."""
        return f"/api/v1/projects/{self.project_id}/models/{model_id}"


def upload(client: TestClient, base: str, role: str, path: Path, name: str | None = None) -> dict:
    """Envia um arquivo pela API e devolve a linha atualizada."""
    resp = client.put(
        f"{base}/{role}",
        params={"filename": name or path.name},
        content=path.read_bytes(),
        headers=OCTET,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def load_pair(
    client: TestClient, corpus: Path, generator: ModuleType, confirm: bool = True
) -> Pair:
    """Cria projeto, envia os dois pares e (opcionalmente) confirma."""
    project = client.post("/api/v1/projects", json={"name": "M4 sintético"}).json()
    ids = {m["discipline"]: m["model_id"] for m in project["models"]}
    pair = Pair(project["project_id"], ids["architecture"], ids["structure"])
    files = {
        "architecture": (generator.ARQ_IFC, generator.ARQ_IDS),
        "structure": (generator.EST_IFC, generator.EST_IDS),
    }
    for discipline, (ifc_name, ids_name) in files.items():
        base = pair.base(ids[discipline])
        upload(client, base, "ifc", corpus / ifc_name)
        binding = upload(client, base, "ids", corpus / ids_name)
        if confirm:
            resp = client.post(
                f"{base}/confirm",
                json={
                    "ifc_revision_id": binding["ifc"]["revision_id"],
                    "ids_revision_id": binding["ids"]["revision_id"],
                },
            )
            assert resp.status_code == 200, resp.text
    return pair


@pytest.fixture
def pair(client: TestClient, corpus_dir: Path, generator: ModuleType) -> Pair:
    """Par sintético carregado e confirmado."""
    return load_pair(client, corpus_dir, generator)
