"""Estudo de formato de contexto (M7-08): casos sintéticos, harness dry-run e modo real travado.

O modo real (inferência no Ollama local) só roda com ``--real`` E
``--confirmo-autorizacao "<quem autorizou, data, meio>"`` (plano M7-10). Sem a confirmação,
o comando sai com código 2 e não abre conexão. As saídas ficam em
``research/M7/estudo-formato-contexto/`` (ignorado pelo git).

Uso:
    uv run python scripts/estudo_formato_contexto.py gerar --seed 20261028 --por-tipo 4
    uv run python scripts/estudo_formato_contexto.py harness --dry-run
    uv run python scripts/estudo_formato_contexto.py modelos            # seleção, sem inferência
    uv run python scripts/estudo_formato_contexto.py harness --real \\
        --confirmo-autorizacao "Cel Giuseppe, 2026-11-03, e-mail"      # inferência
"""

# ruff: noqa: E402 -- execução direta exige incluir a raiz antes dos imports locais.

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
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
    require_mode,
    run_dry,
    write_jsonl,
    write_report,
)
from src.experiment.budget_v1.context_format_runner import (
    DEFAULT_BASE_URL,
    DEFAULT_REPETITIONS,
    DEFAULT_TIMEOUT_S,
    ModelChoice,
    OllamaStructuredClient,
    load_prospection_records,
    run_real,
    select_models,
    summarize_real,
)

CASES_FILE = "casos.jsonl"
REAL_RESULTS = "resultados-real.jsonl"
REAL_REPORT = "relatorio-real.json"
PROSPECTION_DIR = PROJECT_ROOT / "research" / "M7" / "prospection"


def _default_client(base_url: str, timeout_s: float) -> OllamaStructuredClient:
    return OllamaStructuredClient(base_url, timeout_s)


# Fábrica do cliente: substituível nos testes (HTTP simulado), nunca Ollama real em teste.
make_client: Callable[[str, float], OllamaStructuredClient] = _default_client


def _choices(conditioned_decision: str | None) -> list[ModelChoice]:
    return select_models(
        load_prospection_records(PROSPECTION_DIR), conditioned_license_decision=conditioned_decision
    )


def main(argv: list[str] | None = None) -> int:
    """Ponto de entrada da linha de comando; devolve o código de saída."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = parser.add_subparsers(dest="comando", required=True)

    gerar = sub.add_parser("gerar", help="gera o JSONL de casos sintéticos com gabarito")
    gerar.add_argument("--seed", type=int, default=20261028)
    gerar.add_argument("--por-tipo", type=int, default=4, help="casos por (conceito, tipo)")
    gerar.add_argument("--out", type=Path, default=DEFAULT_OUT)

    modelos = sub.add_parser("modelos", help="lista a seleção de modelos (sem inferência)")
    modelos.add_argument("--licenca-condicionada-autorizada", default=None, metavar="REGISTRO")

    harness = sub.add_parser("harness", help="monta prompts, chama (ou simula) e pontua")
    modo = harness.add_mutually_exclusive_group(required=True)
    modo.add_argument("--dry-run", action="store_true", help="respostas simuladas, sem LLM")
    modo.add_argument(
        "--real", action="store_true", help="inferência; exige --confirmo-autorizacao"
    )
    harness.add_argument("--confirmo-autorizacao", default=None, metavar="REGISTRO")
    harness.add_argument("--licenca-condicionada-autorizada", default=None, metavar="REGISTRO")
    harness.add_argument(
        "--modelos", nargs="*", default=None, help="tags (padrão: seleção da M7-09)"
    )
    harness.add_argument("--repeticoes", type=int, default=DEFAULT_REPETITIONS)
    harness.add_argument("--base-url", default=DEFAULT_BASE_URL)
    harness.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S)
    harness.add_argument("--casos", type=Path, default=DEFAULT_OUT / CASES_FILE)
    harness.add_argument("--out", type=Path, default=DEFAULT_OUT)

    args = parser.parse_args(argv)
    if args.comando == "gerar":
        cases = generate_cases(seed=args.seed, per_kind=args.por_tipo)
        path = write_jsonl(cases, args.out / CASES_FILE)
        logger.info("{} casos gravados em {}", len(cases), path)
        return 0

    if args.comando == "modelos":
        for c in _choices(args.licenca_condicionada_autorizada):
            mark = "SELECIONADO" if c.selected else "fora"
            logger.info(
                "{:11} {:32} {} GiB | {}",
                mark,
                c.tag or c.record_id,
                c.estimated_gib,
                "; ".join(c.reasons),
            )
        return 0

    try:
        require_mode("real" if args.real else "dry_run", args.confirmo_autorizacao)
    except RealModeBlocked as exc:
        logger.error("{}", exc)
        return 2
    if not args.casos.exists():
        logger.error("arquivo de casos ausente: {} (rode o subcomando gerar)", args.casos)
        return 1
    cases = read_jsonl(args.casos)

    if args.dry_run:
        reports = run_dry(cases)
        json_path, md_path = write_report(cases, reports, args.out)
        logger.info("dry-run: {} células, relatório em {} e {}", len(reports), json_path, md_path)
        return 0

    tags = args.modelos or [
        c.tag for c in _choices(args.licenca_condicionada_autorizada) if c.selected and c.tag
    ]
    if not tags:
        logger.error("nenhum modelo selecionado")
        return 1
    logger.warning("MODO REAL autorizado por: {} | modelos: {}", args.confirmo_autorizacao, tags)
    results = args.out / REAL_RESULTS
    client = make_client(args.base_url, args.timeout)
    try:
        run_real(
            cases,
            tags,
            results,
            client,
            repetitions=args.repeticoes,
            progress=lambda i, n: logger.info("{}/{}", i, n) if i % 50 == 0 or i == n else None,
        )
    finally:
        client.close()
    summary = [s.model_dump() for s in summarize_real(results, cases)]
    report = {"autorizacao": args.confirmo_autorizacao, "modelos": tags, "celulas": summary}
    report_path = args.out / REAL_REPORT
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    logger.info("modo real concluído: {} células em {}", len(summary), report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
