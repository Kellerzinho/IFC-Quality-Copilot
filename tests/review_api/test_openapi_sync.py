"""O openapi.json versionado precisa refletir a API Python.

Os tipos TypeScript são conferidos contra o mesmo arquivo por
``npm run check:api`` (frontend/scripts/check-api-types.mjs).
"""

from pathlib import Path

from src.review_api.export_openapi import render_openapi

OPENAPI = Path(__file__).resolve().parents[2] / "frontend" / "openapi.json"


def test_versioned_openapi_matches_api() -> None:
    current = OPENAPI.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert current == render_openapi(), (
        "frontend/openapi.json desatualizado: rode `npm run gen:api` em frontend/."
    )


def test_openapi_declares_no_external_servers_or_docs_cdn() -> None:
    text = render_openapi()
    assert '"servers"' not in text
    for cdn in ("cdn.jsdelivr", "unpkg.com", "fastapi.tiangolo.com/img"):
        assert cdn not in text
