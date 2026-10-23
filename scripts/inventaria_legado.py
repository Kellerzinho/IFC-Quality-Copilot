"""Inventário e comparabilidade do legado experimental (tarefa M7-02).

Somente leitura sobre os resultados históricos. Gera:

- ``inventory.json`` — checklist M7-02, conferência de hashes, totais por
  classe/flag/modelo e um ``LegacyRunRecord`` por run;
- ``comparability.csv`` — projeção por run com classe, motivos e flags.

Duas leituras:

- **(b) documental**, padrão: parte do inventário de 12/10/2026 em
  ``docs/pesquisa/modulo-07-avaliacao/`` e reconfere por SHA-256 os runs que
  existem neste clone.
- **(a) pasta legada**: ``--pasta-legada CAMINHO`` confere cada run, sidecar e
  pacote ZIP listado no inventário documental contra o SHA-256 registrado
  (confere / divergente / ausente) e lê as métricas dos runs que conferem. Nada
  é escrito, extraído ou movido dentro da pasta legada.

Não executa inferência, harness nem Ollama.

Uso:

    uv run python scripts/inventaria_legado.py
    uv run python scripts/inventaria_legado.py --pasta-legada "D:\\legado" --saida "C:\\temp\\m7-02"
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.experiment.budget_v1.legacy import (  # noqa: E402
    DOCUMENTAL_CSV,
    DOCUMENTAL_JSON,
    LEGACY_DIR,
    ReadMode,
    build_inventory,
    build_records,
    check_archives,
    csv_consistency,
    ensure_outside,
    load_documental,
    write_outputs,
)


def _sha256(path: Path) -> str:
    """SHA-256 de um arquivo de fonte, para registrar no inventário."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    """Lê o legado (documental ou pasta original) e grava as duas saídas."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--pasta-legada",
        type=Path,
        default=None,
        help="raiz da cópia original do projeto (com src/experiment/results e dist/)",
    )
    parser.add_argument("--saida", type=Path, default=PROJECT_ROOT / LEGACY_DIR)
    args = parser.parse_args(argv)

    mode: ReadMode = "pasta_legada" if args.pasta_legada else "documental"
    root = PROJECT_ROOT
    if args.pasta_legada is not None:
        root = args.pasta_legada
        if not root.is_dir():
            logger.error("pasta legada não encontrada: {}", root)
            return 2
        ensure_outside(args.saida, root)

    documental = load_documental(PROJECT_ROOT)
    csv_text = (PROJECT_ROOT / DOCUMENTAL_CSV).read_text(encoding="utf-8")
    records = build_records(documental, root=root, mode=mode)
    archives = (
        check_archives(root, documental.get("archive_groups") or [])
        if mode == "pasta_legada"
        else []
    )
    inventory = build_inventory(
        documental,
        records,
        mode=mode,
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        sources={
            DOCUMENTAL_JSON.as_posix(): _sha256(PROJECT_ROOT / DOCUMENTAL_JSON),
            DOCUMENTAL_CSV.as_posix(): _sha256(PROJECT_ROOT / DOCUMENTAL_CSV),
        },
        csv_check=csv_consistency(documental, csv_text),
        archive_checks=archives,
    )
    write_outputs(args.saida, inventory)

    totals = inventory["conferencia_totais"]
    if not totals["confere"]:
        logger.warning("totais divergem do esperado: {}", totals["diferenca"])
    check = inventory["checklist"]["validar_artefatos_hashes"]
    logger.info(
        "{} runs ({}); hashes de run {}; saída em {}",
        len(records),
        mode,
        check["runs"],
        args.saida,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
