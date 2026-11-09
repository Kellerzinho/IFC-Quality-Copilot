"""Executor de análise em subprocesso para os testes de lock, concorrência e queda.

Uso: ``python -m tests.operations.analysis_worker MODO BASE SINAL [PEDIDO_JSON]``.
Modos: ``run`` executa normalmente; ``hold_lock`` só detém o coordenador até o sinal;
``wait_in_evaluation`` pausa dentro da avaliação até o sinal; ``crash_in_evaluation``,
``crash_in_final_transaction`` e ``crash_after_commit`` encerram o processo sem
limpeza (``os._exit``) no ponto indicado. ``SINAL.ready`` avisa que o ponto foi
alcançado. Dados SINTÉTICOS de teste; nada aqui é usado fora da suíte.
"""

import os
import sys
import time
from pathlib import Path
from typing import Any

from src.artifacts.storage import LocalArtifactStore
from src.operations.database import OperationalStore
from src.suggestion_engine.catalog_operations import build_e3_operation_bundle
from src.suggestion_engine.catalog_service import CatalogEnrichmentService
from src.validation import catalog_analysis as ca


def _wait(signal: Path) -> None:
    deadline = time.monotonic() + 120
    while not signal.exists():
        if time.monotonic() > deadline:
            raise SystemExit(4)
        time.sleep(0.05)


def _ready(signal: Path) -> None:
    signal.with_suffix(".ready").write_text("ok", encoding="utf-8")


def main(argv: list[str]) -> int:
    """Executa o modo pedido e imprime o recibo JSON quando houver."""
    mode, base, signal = argv[0], Path(argv[1]), Path(argv[2])
    store = OperationalStore.open(base / "db")
    artifacts = LocalArtifactStore(base / "a")
    if mode == "hold_lock":
        with ca.AnalysisCoordinator.acquire(store.root):
            _ready(signal)
            _wait(signal)
        return 0
    request = ca.CatalogAnalysisRequest.model_validate_json(argv[3])
    original_enrich = CatalogEnrichmentService.enrich
    if mode == "wait_in_evaluation":

        def waiting(self: Any, *args: Any, **kwargs: Any) -> Any:
            _ready(signal)
            _wait(signal)
            return original_enrich(self, *args, **kwargs)

        CatalogEnrichmentService.enrich = waiting  # type: ignore[method-assign]
    elif mode == "crash_in_evaluation":

        def crash_eval(self: Any, *args: Any, **kwargs: Any) -> Any:
            _ready(signal)
            os._exit(9)

        CatalogEnrichmentService.enrich = crash_eval  # type: ignore[method-assign]
    elif mode == "crash_in_final_transaction":

        def crash_put(self: Any, *args: Any, **kwargs: Any) -> None:
            _ready(signal)
            os._exit(10)

        ca.CatalogCache.put = crash_put  # type: ignore[method-assign]
    elif mode == "crash_after_commit":
        original_persist = ca._persist

        def crash_persist(*args: Any, **kwargs: Any) -> Any:
            original_persist(*args, **kwargs)
            _ready(signal)
            os._exit(11)

        ca._persist = crash_persist
    elif mode != "run":
        raise SystemExit(f"modo desconhecido: {mode}")
    from src.pipeline import run_catalog_analysis

    receipt = run_catalog_analysis(
        request, store=store, artifacts=artifacts, operation_bundle=build_e3_operation_bundle()
    )
    sys.stdout.write(receipt.model_dump_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
