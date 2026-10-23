"""Exporta o OpenAPI da API de revisão: ``python -m src.review_api.export_openapi <saida>``."""

import json
import sys
import tempfile
from pathlib import Path

from src.review_api.app import create_app


def render_openapi() -> str:
    """Retorna o OpenAPI como JSON estável (indentado, UTF-8, quebra final)."""
    with tempfile.TemporaryDirectory() as tmp:
        schema = create_app(Path(tmp)).openapi()
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    """Grava o OpenAPI no caminho informado."""
    if len(sys.argv) != 2:
        raise SystemExit("uso: python -m src.review_api.export_openapi <arquivo.json>")
    Path(sys.argv[1]).write_text(render_openapi(), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
