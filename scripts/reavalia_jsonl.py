"""Re-avalia resultados por issue já gravados, sem repetir chamadas ao LLM.

Como o ``run_N_issues.jsonl`` guarda o valor esperado e os valores recebidos, uma
mudança de **critério de avaliação** (banda de equivalência numérica, por exemplo)
pode ser aplicada aos runs existentes sem gastar GPU. Isso mantém honesto o
relato do artigo: a mesma coleta de dados pode ser reportada sob a banda estrita
e sob a banda de engenharia, e o leitor vê as duas.

Uso:

    python scripts/reavalia_jsonl.py <dir_do_dataset> [--banda 0.10]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.experiment.per_issue import IssueOutcome, _relative_error_pct, read_outcomes_jsonl


def _erro_pct(outcome: IssueOutcome) -> float | None:
    """Erro relativo do top-1, recalculado do dado bruto quando não foi gravado.

    Runs anteriores à inclusão do campo não têm ``error_pct``, mas gravam
    ``expected`` e ``top_values`` — o suficiente para recomputar.
    """
    if outcome.error_pct is not None:
        return outcome.error_pct
    if not outcome.top_values:
        return None
    return _relative_error_pct(outcome.top_values[0], outcome.expected)


def _rescore(outcome: IssueOutcome, banda_pct: float) -> bool:
    """True se o top-1 casaria sob a banda dada (só afeta estratos numéricos)."""
    erro = _erro_pct(outcome)
    if erro is None:
        return outcome.match_top1
    return erro <= banda_pct


def main(argv: list[str] | None = None) -> int:
    """Reporta top-1 por estrato sob a banda pedida, comparando com o gravado."""
    parser = argparse.ArgumentParser(prog="python scripts/reavalia_jsonl.py")
    parser.add_argument("results_dir", help="Diretório com <modelo>/run_N_issues.jsonl")
    parser.add_argument(
        "--banda",
        type=float,
        default=10.0,
        help="Banda de equivalência em %% para grandezas numéricas (default 10).",
    )
    args = parser.parse_args(argv)

    for jsonl in sorted(Path(args.results_dir).glob("*/run_*_issues.jsonl")):
        outcomes = read_outcomes_jsonl(jsonl)
        if not outcomes:
            continue
        modelo = jsonl.parent.name
        gravado = sum(o.match_top1 for o in outcomes)
        rescored = sum(_rescore(o, args.banda) for o in outcomes)
        n = len(outcomes)
        print(f"\n### {modelo} (n={n})")
        print(f"  top-1 como gravado          : {gravado}/{n} = {gravado / n:.4f}")
        print(f"  top-1 sob banda de {args.banda:.0f}%     : {rescored}/{n} = {rescored / n:.4f}")

        por_estrato: dict[str, list[IssueOutcome]] = {}
        for o in outcomes:
            por_estrato.setdefault(o.stratum, []).append(o)
        for stratum, items in sorted(por_estrato.items(), key=lambda kv: -len(kv[1])):
            erros = [e for e in (_erro_pct(o) for o in items) if e is not None]
            if not erros:
                continue
            antes = sum(o.match_top1 for o in items) / len(items)
            depois = sum(_rescore(o, args.banda) for o in items) / len(items)
            mape = sum(erros) / len(erros)
            print(
                f"    {stratum:<38} n={len(items):>5} "
                f"top1 {antes:.3f} → {depois:.3f} | MAPE {mape:.1f}%"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
