"""Re-pontua runs já coletados sob a comparação categórica corrigida.

Até 2026-07-27 o avaliador comparava ``FireRating`` pelo número embutido, de
modo que ``EI 60``, ``R 60`` e ``REI 60`` casavam entre si. Corrigida a regra,
os números publicados dos runs anteriores mudam — e como o
``run_N_issues.jsonl`` guarda ``expected``, ``accepted_alternatives`` e os
valores recebidos, a re-pontuação não exige repetir uma única chamada ao LLM.

Uso:

    python scripts/rescore_categorico.py src/experiment/results/<run>/<dataset>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.experiment.evaluator import tolerance_for_issue, values_match
from src.experiment.per_issue import IssueOutcome, read_outcomes_jsonl
from src.models import Issue


def _issue_de(outcome: IssueOutcome) -> Issue:
    """Reconstrói o mínimo de Issue que a normalização/comparação consulta."""
    return Issue(
        element_guid=outcome.element_guid,
        element_class=outcome.element_class,
        element_name=None,
        issue_type=outcome.issue_type,  # type: ignore[arg-type]
        severity="medium",
        description="",
        context={"check_property": outcome.check_property},
    )


def _acerta(outcome: IssueOutcome, ate: int) -> bool:
    """Recalcula o acerto do outcome considerando as ``ate`` primeiras opções.

    Usa a MESMA banda por propriedade do ``Evaluator`` (``tolerance_for_issue``);
    chamar ``values_match`` com a tolerância padrão aplicaria 2% ao estrato
    térmico, que tem banda declarada de 10%, e zeraria o estrato inteiro.
    """
    issue = _issue_de(outcome)
    tolerancia = tolerance_for_issue(issue)
    aceitos = [outcome.expected, *outcome.accepted_alternatives]
    for valor in outcome.top_values[:ate]:
        if any(values_match(issue, valor, alvo, tolerancia) for alvo in aceitos):
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    """Compara top-1/top-3 gravados com os recalculados, por estrato."""
    parser = argparse.ArgumentParser(prog="python scripts/rescore_categorico.py")
    parser.add_argument("results_dir", help="Diretório com <modelo>/run_N_issues.jsonl")
    args = parser.parse_args(argv)

    for jsonl in sorted(Path(args.results_dir).glob("*/run_*_issues.jsonl")):
        outcomes = read_outcomes_jsonl(jsonl)
        if not outcomes:
            continue
        modelo = jsonl.parent.name
        n = len(outcomes)
        grav1 = sum(o.match_top1 for o in outcomes)
        novo1 = sum(_acerta(o, 1) for o in outcomes)
        novo3 = sum(_acerta(o, 3) for o in outcomes)
        print(f"\n### {modelo} (n={n})")
        print(f"  top-1 gravado     : {grav1}/{n} = {grav1 / n:.4f}")
        print(f"  top-1 recalculado : {novo1}/{n} = {novo1 / n:.4f}")
        print(f"  top-3 recalculado : {novo3}/{n} = {novo3 / n:.4f}")

        por_estrato: dict[str, list[IssueOutcome]] = {}
        for o in outcomes:
            por_estrato.setdefault(o.stratum, []).append(o)
        for stratum, items in sorted(por_estrato.items(), key=lambda kv: -len(kv[1])):
            antes = sum(o.match_top1 for o in items) / len(items)
            depois = sum(_acerta(o, 1) for o in items) / len(items)
            marca = "  <== MUDOU" if abs(antes - depois) > 1e-9 else ""
            print(f"    {stratum:<38} n={len(items):>5} {antes:.3f} -> {depois:.3f}{marca}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
