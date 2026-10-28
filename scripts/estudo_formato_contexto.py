"""Estudo de formato de contexto (M7-08): gera casos sintéticos e roda o harness em dry-run.

Nenhuma inferência: o modo real está bloqueado até autorização (plano M7-10). As saídas
ficam em ``research/M7/estudo-formato-contexto/`` (ignorado pelo git).

Uso:
    uv run python scripts/estudo_formato_contexto.py gerar --seed 20261028 --por-tipo 4
    uv run python scripts/estudo_formato_contexto.py harness --dry-run
    uv run python scripts/estudo_formato_contexto.py harness --real   # recusado
"""

# ruff: noqa: E402 -- execução direta exige incluir a raiz antes dos imports locais.

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from loguru import logger

from src.experiment.budget_v1.context_format import (
    DEFAULT_OUT,
    RealModeBlocked,
    generate_cases,
    read_jsonl,
    require_dry_run,
    run_dry,
    write_jsonl,
    write_report,
)

CASES_FILE = "casos.jsonl"


def main(argv: list[str] | None = None) -> int:
    """Ponto de entrada da linha de comando; devolve o código de saída."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="comando", required=True)

    gerar = sub.add_parser("gerar", help="gera o JSONL de casos sintéticos com gabarito")
    gerar.add_argument("--seed", type=int, default=20261028)
    gerar.add_argument("--por-tipo", type=int, default=4, help="casos por (conceito, tipo)")
    gerar.add_argument("--out", type=Path, default=DEFAULT_OUT)

    harness = sub.add_parser("harness", help="monta prompts, conta tokens e pontua respostas")
    modo = harness.add_mutually_exclusive_group(required=True)
    modo.add_argument("--dry-run", action="store_true", help="respostas simuladas, sem LLM")
    modo.add_argument("--real", action="store_true", help="BLOQUEADO até autorização")
    harness.add_argument("--casos", type=Path, default=DEFAULT_OUT / CASES_FILE)
    harness.add_argument("--out", type=Path, default=DEFAULT_OUT)

    args = parser.parse_args(argv)
    if args.comando == "gerar":
        cases = generate_cases(seed=args.seed, per_kind=args.por_tipo)
        path = write_jsonl(cases, args.out / CASES_FILE)
        logger.info("{} casos gravados em {}", len(cases), path)
        return 0

    try:
        require_dry_run("dry_run" if args.dry_run else "real")
    except RealModeBlocked as exc:
        logger.error("{}", exc)
        return 2
    if not args.casos.exists():
        logger.error("arquivo de casos ausente: {} (rode o subcomando gerar)", args.casos)
        return 1
    cases = read_jsonl(args.casos)
    reports = run_dry(cases)
    json_path, md_path = write_report(cases, reports, args.out)
    logger.info("dry-run: {} células, relatório em {} e {}", len(reports), json_path, md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
