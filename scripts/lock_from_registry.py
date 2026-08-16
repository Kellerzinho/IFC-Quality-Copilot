"""Gera ``models.lock.json`` (schema v2) direto do registry oficial do Ollama.

Autoria remota: para um lock cujos modelos nao cabem na maquina local (caso do
lock escala-4070), o ``ollama pull`` local e inviavel (~92 GB). O digest pinavel
e o SHA-256 dos bytes crus do manifest servido por ``registry.ollama.ai``, e o
``size_bytes`` e a soma ``config.size + soma(layers[].size)`` — exatamente os
valores que ``/api/tags`` reporta apos o pull. Metodo validado byte a byte
contra as 10 entradas do lock do par unificado v7.7 (digest, size_bytes,
architecture, parameters e quantization identicos; ver
``docs/condicao-escala-4070-2026-08-16.md`` §5).

O ``context_length`` nao existe no manifest nem no config blob (vive no
cabecalho GGUF do blob do modelo), entao cada modelo declara o valor no
argumento, conferido contra a pagina oficial da tag em ollama.com — a mesma
fonte que ``ollama show`` le apos o download.

Uso (a ordem dos argumentos vira a ordem oficial da fila do benchmark):

    uv run python scripts/lock_from_registry.py \\
        falcon3:10b@32768 mistral-nemo:12b@1024000 [...]

O bloco ``runtime`` (Ollama pinado) e preservado do lock existente: este
script troca a populacao de modelos, nunca o runtime.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.experiment.model_lock import (  # noqa: E402
    ModelMatrixLock,
    required_free_bytes,
)

REGISTRY = "https://registry.ollama.ai/v2/library"
MANIFEST_ACCEPT = "application/vnd.docker.distribution.manifest.v2+json"
LOCK_PATH = PROJECT_ROOT / "src" / "experiment" / "results" / "models.lock.json"


@dataclass(frozen=True)
class ModelSpec:
    """Tag Ollama e o context_length declarado para uma entrada do lock."""

    name: str
    context_length: int


def parse_spec(argument: str) -> ModelSpec:
    """Interpreta um argumento ``name:tag@context_length``."""
    name, separator, raw_context = argument.partition("@")
    if not separator or ":" not in name:
        raise ValueError(f"argumento deve ser name:tag@context_length: {argument!r}")
    context_length = int(raw_context)
    if context_length <= 0:
        raise ValueError(f"context_length deve ser positivo: {argument!r}")
    return ModelSpec(name=name, context_length=context_length)


def fetch_lock_entry(client: httpx.Client, spec: ModelSpec) -> dict[str, object]:
    """Monta uma entrada do lock a partir do manifest e do config blob remotos."""
    repository, _, tag = spec.name.partition(":")
    manifest_response = client.get(
        f"{REGISTRY}/{repository}/manifests/{tag}",
        headers={"Accept": MANIFEST_ACCEPT},
    )
    manifest_response.raise_for_status()
    digest = sha256(manifest_response.content).hexdigest()
    manifest = manifest_response.json()

    layers = manifest["layers"]
    size_bytes = int(manifest["config"]["size"]) + sum(int(layer["size"]) for layer in layers)

    config_response = client.get(f"{REGISTRY}/{repository}/blobs/{manifest['config']['digest']}")
    config_response.raise_for_status()
    config = config_response.json()

    return {
        "name": spec.name,
        "digest": digest,
        "size_bytes": size_bytes,
        "architecture": str(config["model_family"]),
        "parameters": str(config["model_type"]),
        "context_length": spec.context_length,
        "quantization": str(config["file_type"]),
    }


def main(argv: list[str] | None = None) -> int:
    """Gera, valida e grava o lock; imprime os totais citaveis."""
    arguments = sys.argv[1:] if argv is None else argv
    if not arguments:
        print(__doc__, file=sys.stderr)
        return 1

    try:
        specs = [parse_spec(argument) for argument in arguments]
    except ValueError as error:
        print(f"ERRO: {error}", file=sys.stderr)
        return 1

    runtime = json.loads(LOCK_PATH.read_text(encoding="utf-8"))["runtime"]

    entries: list[dict[str, object]] = []
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        for spec in specs:
            entry = fetch_lock_entry(client, spec)
            entries.append(entry)
            print(
                f"  {spec.name:24} {str(entry['digest'])[:12]}  "
                f"{int(entry['size_bytes']) / 1e9:6.2f} GB  "
                f"{entry['architecture']:14} {entry['parameters']:>6} "
                f"{entry['quantization']}"
            )

    document = {"schema_version": 2, "runtime": runtime, "models": entries}
    lock = ModelMatrixLock.model_validate(document)

    LOCK_PATH.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    total = sum(model.size_bytes for model in lock.models)
    print(f"\nlock gravado: {LOCK_PATH} ({len(lock.models)} modelos)")
    print(f"soma size_bytes       = {total:_}")
    print(f"required_free_bytes({{}}) = {required_free_bytes(lock, {}):_}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
