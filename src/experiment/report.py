"""Relatório do benchmark: tabelas e figuras a partir dos run_*.json (Fase B.4).

Agrega os ``ExperimentResult`` exportados pelo runner em
``results/<data>/<modelo>/run_<n>.json`` e produz:

- tabela consolidada por modelo (média ± desvio entre réplicas) em Markdown e
  LaTeX — nenhum número do artigo é digitado à mão;
- figuras Plotly (HTML autocontido): barras de acurácia top-1/top-3 por modelo
  e dispersão qualidade × latência.

Uso:

    python -m src.experiment.report \\
        --results src/experiment/results/2026-07-10 \\
        --output src/experiment/results/2026-07-10/report
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from loguru import logger

# Paleta categórica validada (ordem fixa por slot — a ordem é o mecanismo de
# segurança CVD; cor segue o modelo, nunca o rank). Superfície e tintas do
# sistema de referência do projeto de visualização.
_SERIES = ["#2a78d6", "#1baf7a", "#eda100", "#008300", "#4a3aa7", "#e34948"]
_SURFACE = "#fcfcfb"
_INK = "#0b0b0b"
_INK_MUTED = "#898781"
_GRID = "#e1e0d9"

_METRIC_COLUMNS = [
    ("accuracy_top1", "Top-1 ocorr."),
    ("accuracy_top3", "Top-3 ocorr."),
    ("accuracy_equivalence_top1", "Top-1 equival."),
    ("accuracy_equivalence_top3", "Top-3 equival."),
    ("accuracy_high_top1", "Top-1 high"),
    ("accuracy_medium_top1", "Top-1 medium"),
    ("accuracy_low_top1", "Top-1 low"),
    ("accuracy_legacy_top1", "Top-1 legado"),
    ("occurrence_count", "Ocorrências"),
    ("equivalence_count", "Equivalências"),
    ("precision", "Precisão"),
    ("ids_conformity_rate", "Conform. IDS"),
    ("json_valid_first_try_rate", "JSON 1ª tent."),
    ("avg_attempts", "Tentativas (méd.)"),
    ("latency_ms_p50", "Latência p50 (ms)"),
    ("latency_ms_p95", "Latência p95 (ms)"),
    ("acceptance_rate", "Aceitação (proxy)"),
    ("review_rate", "Revisão (proxy)"),
]


def load_results(results_dir: str | Path) -> pd.DataFrame:
    """Carrega todos os ``run_*.json`` sob ``results_dir`` em um DataFrame plano.

    Uma linha por réplica, com as métricas de qualidade, estabilidade,
    eficiência e proxy de revisão achatadas por prefixo.
    """
    rows: list[dict] = []
    for path in sorted(Path(results_dir).glob("*/run_*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        evaluation = data["evaluation"]
        equivalence = evaluation.get("accuracy_equivalence")
        has_equivalence = isinstance(equivalence, dict)
        if not has_equivalence:
            equivalence = {
                "top1": evaluation["accuracy_top1"],
                "top3": evaluation["accuracy_top3"],
                "total": evaluation.get("total_evaluated", 0),
            }
        confidence = evaluation.get("accuracy_by_confidence", {})
        legacy = evaluation.get("accuracy_legacy", {})
        accuracy_all = evaluation.get("accuracy_all", {})
        rows.append(
            {
                "model": data["metadata"]["model_name"],
                "replica": data["metadata"]["replica_index"],
                "accuracy_top1": data["evaluation"]["accuracy_top1"],
                "accuracy_top3": data["evaluation"]["accuracy_top3"],
                "accuracy_equivalence_top1": equivalence["top1"],
                "accuracy_equivalence_top3": equivalence["top3"],
                "accuracy_high_top1": confidence.get("high", {}).get("top1", 0.0),
                "accuracy_medium_top1": confidence.get("medium", {}).get("top1", 0.0),
                "accuracy_low_top1": confidence.get("low", {}).get("top1", 0.0),
                "accuracy_legacy_top1": legacy.get("top1", 0.0),
                "occurrence_count": accuracy_all.get(
                    "total", evaluation.get("total_evaluated", 0)
                ),
                "equivalence_count": equivalence["total"],
                "metric_basis": (
                    "equivalence" if has_equivalence else "legacy_occurrence"
                ),
                "precision": data["evaluation"]["precision"],
                "total_evaluated": data["evaluation"]["total_evaluated"],
                "ids_conformity_rate": data["review_proxy"]["ids_conformity_rate"],
                "acceptance_rate": data["review_proxy"]["acceptance_rate"],
                "review_rate": data["review_proxy"]["review_rate"],
                "json_valid_first_try_rate": data["stability"]["json_valid_first_try_rate"],
                "avg_attempts": data["stability"]["avg_attempts"],
                "failure_rate": data["stability"]["failure_rate"],
                "latency_ms_p50": data["timing"]["latency_ms_p50"],
                "latency_ms_p95": data["timing"]["latency_ms_p95"],
                "output_tokens_per_sample": data["timing"]["output_tokens_per_sample"],
                "source": str(path),
            }
        )
    if not rows:
        raise FileNotFoundError(f"Nenhum run_*.json encontrado sob {results_dir}")
    return pd.DataFrame(rows)


def aggregate(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega por modelo: média e desvio-padrão entre réplicas.

    Colunas de saída: ``<métrica>_mean`` e ``<métrica>_std`` para cada métrica,
    mais ``replicas`` (contagem). Ordenado por top-1 média decrescente.
    """
    metrics = [col for col, _ in _METRIC_COLUMNS]
    grouped = df.groupby("model")[metrics].agg(["mean", "std"])
    grouped.columns = [f"{col}_{stat}" for col, stat in grouped.columns]
    grouped["replicas"] = df.groupby("model")["replica"].count()
    grouped["metric_basis"] = df.groupby("model")["metric_basis"].agg(
        lambda values: (
            "equivalence" if set(values) == {"equivalence"} else "legacy_occurrence"
        )
    )
    return grouped.sort_values(
        "accuracy_equivalence_top1_mean", ascending=False
    ).reset_index()


def _fmt(mean: float, std: float, pct: bool) -> str:
    """Formata média ± desvio; percentuais com 1 casa, demais com 2."""
    if pct:
        base = f"{mean * 100:.1f}%"
        return base if pd.isna(std) else f"{base} ± {std * 100:.1f}"
    base = f"{mean:,.0f}" if mean >= 100 else f"{mean:.2f}"
    if pd.isna(std):
        return base
    return f"{base} ± {std:,.0f}" if mean >= 100 else f"{base} ± {std:.2f}"


def to_markdown(agg: pd.DataFrame) -> str:
    """Tabela Markdown consolidada por modelo (média ± desvio entre réplicas)."""
    header = ["Modelo", "n"] + [label for _, label in _METRIC_COLUMNS]
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for _, row in agg.iterrows():
        cells = [str(row["model"]), str(int(row["replicas"]))]
        for col, _label in _METRIC_COLUMNS:
            pct = not col.startswith(("latency", "avg_")) and not col.endswith("_count")
            cells.append(_fmt(row[f"{col}_mean"], row[f"{col}_std"], pct))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def to_latex(agg: pd.DataFrame) -> str:
    """Tabela LaTeX (booktabs) consolidada por modelo."""
    cols = "l r " + "r " * len(_METRIC_COLUMNS)
    lines = [
        f"\\begin{{tabular}}{{{cols.strip()}}}",
        "\\toprule",
        "Modelo & $n$ & " + " & ".join(label for _, label in _METRIC_COLUMNS) + " \\\\",
        "\\midrule",
    ]
    for _, row in agg.iterrows():
        cells = [str(row["model"]).replace("_", "\\_"), str(int(row["replicas"]))]
        for col, _label in _METRIC_COLUMNS:
            pct = not col.startswith(("latency", "avg_")) and not col.endswith("_count")
            cells.append(_fmt(row[f"{col}_mean"], row[f"{col}_std"], pct).replace("%", "\\%"))
        lines.append(" & ".join(cells) + " \\\\")
    lines += ["\\bottomrule", "\\end{tabular}"]
    return "\n".join(lines)


def _base_layout(title: str) -> dict:
    """Layout Plotly comum: superfície clara, grid recessivo, tinta do sistema."""
    return {
        "title": {"text": title, "font": {"color": _INK, "size": 16}},
        "paper_bgcolor": _SURFACE,
        "plot_bgcolor": _SURFACE,
        "font": {"color": _INK, "family": "system-ui, 'Segoe UI', sans-serif"},
        "xaxis": {"gridcolor": _GRID, "linecolor": _GRID, "tickfont": {"color": _INK_MUTED}},
        "yaxis": {"gridcolor": _GRID, "linecolor": _GRID, "tickfont": {"color": _INK_MUTED}},
        "legend": {"orientation": "h", "y": -0.2},
        "bargap": 0.35,
    }


def figure_topk_bars(agg: pd.DataFrame) -> go.Figure:
    """Barras agrupadas: acurácia top-1 e top-3 por modelo (2 séries + legenda)."""
    fig = go.Figure()
    fig.add_bar(
        name="Top-1",
        x=agg["model"],
        y=agg["accuracy_top1_mean"],
        error_y={"type": "data", "array": agg["accuracy_top1_std"].fillna(0)},
        marker={"color": _SERIES[0]},
    )
    fig.add_bar(
        name="Top-3",
        x=agg["model"],
        y=agg["accuracy_top3_mean"],
        error_y={"type": "data", "array": agg["accuracy_top3_std"].fillna(0)},
        marker={"color": _SERIES[1]},
    )
    layout = _base_layout("Acurácia por modelo (média ± desvio entre réplicas)")
    layout["yaxis"]["tickformat"] = ".0%"
    layout["yaxis"]["range"] = [0, 1]
    fig.update_layout(**layout)
    return fig


def figure_quality_latency(agg: pd.DataFrame) -> go.Figure:
    """Dispersão qualidade (top-1) × latência p50 — um ponto por modelo.

    Cor segue o modelo em ordem fixa de slot; rótulos diretos em vez de
    depender só da cor (regra de acessibilidade).
    """
    fig = go.Figure()
    for idx, (_, row) in enumerate(agg.iterrows()):
        fig.add_scatter(
            x=[row["latency_ms_p50_mean"] / 1000.0],
            y=[row["accuracy_equivalence_top1_mean"]],
            mode="markers+text",
            name=str(row["model"]),
            text=[str(row["model"])],
            textposition="top center",
            textfont={"color": _INK, "size": 12},
            marker={"size": 12, "color": _SERIES[idx % len(_SERIES)]},
        )
    layout = _base_layout("Qualidade × latência (p50) por modelo")
    layout["xaxis"]["title"] = {
        "text": "Latência p50 por sugestão (s)",
        "font": {"color": _INK_MUTED},
    }
    layout["yaxis"]["title"] = {
        "text": "Acurácia top-1 por equivalência",
        "font": {"color": _INK_MUTED},
    }
    layout["yaxis"]["tickformat"] = ".0%"
    layout["showlegend"] = False  # rótulos diretos nos pontos
    fig.update_layout(**layout)
    return fig


def generate_report(results_dir: str | Path, output_dir: str | Path) -> dict[str, Path]:
    """Gera tabelas (md/tex/csv) e figuras (html) e retorna os caminhos criados."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    df = load_results(results_dir)
    agg = aggregate(df)

    paths = {
        "raw_csv": out / "runs_raw.csv",
        "table_md": out / "results_table.md",
        "table_tex": out / "results_table.tex",
        "fig_topk": out / "fig_topk_bars.html",
        "fig_quality_latency": out / "fig_quality_latency.html",
    }
    df.to_csv(paths["raw_csv"], index=False, encoding="utf-8")
    paths["table_md"].write_text(to_markdown(agg) + "\n", encoding="utf-8")
    paths["table_tex"].write_text(to_latex(agg) + "\n", encoding="utf-8")
    figure_topk_bars(agg).write_html(paths["fig_topk"], include_plotlyjs="cdn")
    figure_quality_latency(agg).write_html(paths["fig_quality_latency"], include_plotlyjs="cdn")

    logger.info("report: {} réplicas de {} modelos → {}", len(df), agg.shape[0], out)
    return paths


def main(argv: list[str] | None = None) -> int:
    """CLI do relatório do benchmark."""
    parser = argparse.ArgumentParser(
        prog="python -m src.experiment.report",
        description="Gera tabelas e figuras do benchmark a partir dos run_*.json.",
    )
    parser.add_argument("--results", required=True, help="Diretório com <modelo>/run_*.json")
    parser.add_argument("--output", required=True, help="Diretório de saída do relatório")
    args = parser.parse_args(argv)
    generate_report(args.results, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
