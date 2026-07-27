"""Breakdown por estrato dos resultados por issue (P1).

Lê os ``run_*_issues.jsonl`` de um diretório de resultados e reporta top-1,
top-3, abstenção e estímulos distintos **por estrato** (``issue_type/propriedade``),
que é a unidade em que a tarefa muda de natureza. O agregado sozinho não
distingue "tudo mediano" de "um estrato ótimo e outro zerado".

Também compara modelos lado a lado no mesmo estrato e, com ``--pareado``,
aplica McNemar exato entre dois modelos sobre as issues que ambos avaliaram —
o teste correto quando as observações são pareadas (mesmas issues).

Uso:

    python scripts/breakdown_estratos.py src/experiment/results/<run>/<dataset>
    python scripts/breakdown_estratos.py <dir> --pareado gemma2:9b qwen2.5:7b-instruct
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.experiment.per_issue import (
    IssueOutcome,
    aggregate_by_stratum,
    paired_comparison,
    read_outcomes_jsonl,
)


def _carregar(results_dir: Path) -> dict[str, list[IssueOutcome]]:
    """Mapeia ``modelo -> outcomes`` lendo todos os run_*_issues.jsonl do diretório."""
    por_modelo: dict[str, list[IssueOutcome]] = {}
    for jsonl in sorted(results_dir.glob("*/run_*_issues.jsonl")):
        modelo = jsonl.parent.name
        por_modelo.setdefault(modelo, []).extend(read_outcomes_jsonl(jsonl))
    return por_modelo


def _tabela_por_modelo(modelo: str, outcomes: list[IssueOutcome]) -> None:
    """Imprime o breakdown por estrato de um modelo."""
    linhas = aggregate_by_stratum(outcomes)
    total = len(outcomes)
    acertos = sum(o.match_top1 for o in outcomes)
    print(f"\n### {modelo} — top-1 global {acertos}/{total} = {acertos / total:.4f}")
    print(
        f"{'estrato':<38} {'n':>5} {'estim':>6} {'top1':>7} {'top3':>7} {'abst':>6} "
        f"{'MAPE%':>8} {'<=10%':>7} {'<=20%':>7}"
    )
    print("-" * 100)
    for row in linhas:
        # Colunas continuas so existem em estrato com esperado numerico.
        mape = f"{row['mape']:>8.1f}" if "mape" in row else f"{'—':>8}"
        d10 = f"{row['dentro_10pct']:>7.3f}" if "dentro_10pct" in row else f"{'—':>7}"
        d20 = f"{row['dentro_20pct']:>7.3f}" if "dentro_20pct" in row else f"{'—':>7}"
        print(
            f"{row['stratum']:<38} {row['n']:>5} {row['estimulos']:>6} "
            f"{row['top1']:>7.3f} {row['top3']:>7.3f} {row['abstencao']:>6.3f} "
            f"{mape} {d10} {d20}"
        )


def _comparativo(por_modelo: dict[str, list[IssueOutcome]]) -> None:
    """Imprime top-1 por estrato com os modelos lado a lado."""
    estratos: list[str] = []
    for outcomes in por_modelo.values():
        for row in aggregate_by_stratum(outcomes):
            if row["stratum"] not in estratos:
                estratos.append(row["stratum"])

    modelos = list(por_modelo)
    print(f"\n### top-1 por estrato ({len(modelos)} modelos)")
    cabecalho = f"{'estrato':<38} " + " ".join(f"{m[:14]:>15}" for m in modelos)
    print(cabecalho)
    print("-" * len(cabecalho))
    for stratum in estratos:
        celulas = []
        for modelo in modelos:
            row = next(
                (r for r in aggregate_by_stratum(por_modelo[modelo]) if r["stratum"] == stratum),
                None,
            )
            celulas.append(f"{row['top1']:>15.3f}" if row else f"{'—':>15}")
        print(f"{stratum:<38} " + " ".join(celulas))


def _pareado(por_modelo: dict[str, list[IssueOutcome]], a: str, b: str) -> None:
    """Compara dois modelos com McNemar exato sobre as issues que ambos avaliaram."""
    if a not in por_modelo or b not in por_modelo:
        print(f"\n[pareado] modelo ausente: {a if a not in por_modelo else b}")
        print(f"[pareado] disponíveis: {', '.join(por_modelo)}")
        return

    print(f"\n### McNemar pareado: {a} vs {b}")
    for unit, rotulo in (("stimulus", "ESTIMULO (correto)"), ("issue", "issue (inflado)")):
        r = paired_comparison(por_modelo[a], por_modelo[b], unit=unit)
        veredicto = "← significativo" if r["p_value"] < 0.05 else "(nao significativo)"
        print(f"  [{rotulo}] n={r['n']} | ambos={r['ambos']} | "
              f"so {a[:16]}={r['so_a']} | so {b[:16]}={r['so_b']} | "
              f"p={r['p_value']:.4f} {veredicto}")
    print("  Reportar a linha de ESTIMULO: com reuso, uma resposta do LLM e copiada")
    print("  para todas as issues equivalentes, e contar as copias trata replicacao")
    print("  como evidencia independente.")


def main(argv: list[str] | None = None) -> int:
    """Ponto de entrada do breakdown."""
    parser = argparse.ArgumentParser(prog="python scripts/breakdown_estratos.py")
    parser.add_argument("results_dir", help="Diretório com <modelo>/run_N_issues.jsonl")
    parser.add_argument(
        "--pareado",
        nargs=2,
        metavar=("MODELO_A", "MODELO_B"),
        default=None,
        help="Aplica McNemar exato entre dois modelos (nomes de pasta).",
    )
    args = parser.parse_args(argv)

    results_dir = Path(args.results_dir)
    por_modelo = _carregar(results_dir)
    if not por_modelo:
        print(f"Nenhum run_*_issues.jsonl encontrado em {results_dir}")
        print("Runs anteriores a 2026-07-27 só gravaram agregados — precisam ser refeitos.")
        return 1

    for modelo, outcomes in por_modelo.items():
        _tabela_por_modelo(modelo, outcomes)

    if len(por_modelo) > 1:
        _comparativo(por_modelo)

    if args.pareado:
        _pareado(por_modelo, args.pareado[0], args.pareado[1])

    return 0


if __name__ == "__main__":
    sys.exit(main())
