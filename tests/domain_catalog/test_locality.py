"""Localidade do catálogo (M1-06): sem rede, sem cliente bSDD legado, sem fallback.

Usa pacote SINTÉTICO. O bloqueio é mais forte que a fixture global ``block_real_http``,
que só intercepta httpx: aqui qualquer socket ou resolução de nome falha o teste.
"""

import socket
import subprocess
import sys
from pathlib import Path

import pytest

from src.config import BASE_DIR
from src.domain_catalog.contracts import BindingQuery, BindingRequest, CatalogQuery
from src.domain_catalog.reader import open_catalog
from tests.domain_catalog import factories as f

_FORBIDDEN_MODULES = (
    "httpx",
    "ollama",
    "src.bsdd",
    "src.bsdd.client",
    "src.semantic_registry",
    "src.suggestion_engine",
    "src.pipeline",
)


def _exercise(ref_and_path: tuple[object, Path]) -> None:
    ref, path = ref_and_path
    reader = open_catalog(ref, path)  # type: ignore[arg-type]
    reader.describe()
    reader.search(CatalogQuery(text="metodo"))
    reader.list_bindings(BindingQuery(entity="IfcWall"))
    reader.resolve_binding(
        BindingRequest(
            ifc_schema="IFC2X3",
            facet="property",
            set_name="SYN_Qto",
            field_name="Heigth",
            entity="IfcWallStandardCase",
        )
    )
    reader.get_capability("literal_read")


def test_reader_works_with_every_socket_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = f.write_synthetic_release(tmp_path)

    def _no_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("o catálogo tentou acessar a rede")

    monkeypatch.setattr(socket.socket, "connect", _no_network)
    monkeypatch.setattr(socket, "create_connection", _no_network)
    monkeypatch.setattr(socket, "getaddrinfo", _no_network)

    _exercise(release)


def test_reader_never_builds_the_legacy_bsdd_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.bsdd.client as legacy

    release = f.write_synthetic_release(tmp_path)

    def _forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("o catálogo instanciou o BSDDClient legado")

    monkeypatch.setattr(legacy.BSDDClient, "__init__", _forbidden)

    _exercise(release)


def test_catalog_modules_do_not_import_network_or_legacy_semantics() -> None:
    code = (
        "import sys\n"
        "import src.domain_catalog.reader, src.domain_catalog.package\n"
        "import src.domain_catalog.importers.daiane\n"
        f"print(','.join(m for m in {_FORBIDDEN_MODULES!r} if m in sys.modules))\n"
    )

    loaded = subprocess.run(
        [sys.executable, "-c", code], cwd=BASE_DIR, capture_output=True, text=True, check=True
    ).stdout.strip()

    assert loaded == ""
