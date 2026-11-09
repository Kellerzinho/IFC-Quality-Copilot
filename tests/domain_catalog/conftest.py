"""Integrações com fontes externas exigem opt-in e entradas locais completas."""

import os
from pathlib import Path

import pytest

EXTERNAL_INPUTS = (
    "data/catalogs/fixtures/daiane-e1-rascunho/rascunho.json",
    "data/catalogs/sources/daiane-2025/appendix-b-v1.json",
    "data/catalogs/profiles/daiane-e4/reconciliation-v1.json",
    "data/catalogs/profiles/daiane-e4/candidates-v1.json",
    "docs/catalogo/e4/projecoes-daiane.json",
    "docs/catalogo/projecoes-daiane.json",
)


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item: pytest.Item) -> None:
    """Pula somente opt-in ausente; entrada ausente no opt-in é falha explícita."""
    if item.get_closest_marker("external_data") is None:
        return
    if os.environ.get("IFCQC_RUN_EXTERNAL_CATALOG_TESTS") != "1":
        pytest.skip("fontes reais externas: requer IFCQC_RUN_EXTERNAL_CATALOG_TESTS=1")
    root = Path(__file__).resolve().parents[2]
    missing = [name for name in EXTERNAL_INPUTS if not (root / name).is_file()]
    if missing:
        pytest.fail("integração externa solicitada sem entradas: " + ", ".join(missing))
