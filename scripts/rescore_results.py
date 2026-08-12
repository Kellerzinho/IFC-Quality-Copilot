"""Re-pontua coletas já gravadas contra um ground truth emendado.

Uma emenda de ground truth muda o **critério de avaliação**, não a coleta: as
respostas dos modelos continuam sendo exatamente as mesmas. Repetir o benchmark
para medir o efeito da emenda gastaria horas de GPU e ainda misturaria o efeito
da emenda com o de qualquer outra mudança do instrumento.

Este script lê os ``run_*_issues.jsonl`` de uma execução, recompara ``top_values``
contra o ground truth informado e reporta o delta por modelo e por estrato. Não
escreve nada nos resultados originais.

Uso:
    python scripts/rescore_results.py <resultados/> --ground-truth-root data/evaluation
    python scripts/rescore_results.py <resultados/> --json saida.json

O comparador usado é o do repositório no momento da execução. Para isolar o
efeito da **emenda** do efeito de mudanças no comparador, rode o script na
revisão em que o comparador ainda é o da coleta (ver
``docs/emenda-gt-2026-08-12.md`` §5).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.experiment.evaluator import (  # noqa: E402
    DEFAULT_FLOAT_TOLERANCE,
    TOLERANCE_BY_PROPERTY,
    GroundTruth,
    values_match,
)
from src.models import Issue  # noqa: E402


@dataclass
class Tally:
    """Acumulador de acertos antes e depois da emenda."""

    total: int = 0
    top1_antes: int = 0
    top1_depois: int = 0
    top3_antes: int = 0
    top3_depois: int = 0
    mudaram: list[str] = field(default_factory=list)

    def taxa(self, hits: int) -> float:
        return hits / self.total if self.total else 0.0


def _issue_for(registro: dict[str, Any]) -> Issue:
    """Reconstrói o mínimo de Issue que o comparador consulta."""
    return Issue(
        element_guid=registro.get("element_guid") or "0" * 22,
        element_class=registro.get("element_class") or "IfcBuildingElement",
        issue_type=registro.get("issue_type") or "pset_missing",
        severity="medium",
        description="rescore",
        context={"check_property": registro.get("check_property") or ""},
    )


def _tolerancia(registro: dict[str, Any]) -> float:
    return TOLERANCE_BY_PROPERTY.get(
        str(registro.get("check_property") or ""), DEFAULT_FLOAT_TOLERANCE
    )


def _casa(registro: dict[str, Any], aceitos: list[Any], valores: list[Any]) -> bool:
    issue = _issue_for(registro)
    tol = _tolerancia(registro)
    return any(
        values_match(issue, candidato, aceito, tol)
        for candidato in valores
        for aceito in aceitos
    )


def carregar_ground_truth(caminho: Path) -> dict[str, dict[str, Any]]:
    """Indexa o ground truth por ``issue_id``."""
    gt = GroundTruth.from_yaml(str(caminho))
    return {item.issue_id: item for item in gt.items if item.issue_id}


def repontuar(
    results_root: Path, ground_truth_root: Path
) -> tuple[dict[str, Tally], dict[str, Tally]]:
    """Percorre os JSONL da execução e acumula o delta por modelo e por estrato."""
    por_modelo: dict[str, Tally] = defaultdict(Tally)
    por_estrato: dict[str, Tally] = defaultdict(Tally)

    for jsonl in sorted(results_root.rglob("run_*_issues.jsonl")):
        relativo = jsonl.relative_to(results_root).parts
        if len(relativo) < 2:
            continue
        dataset, modelo = relativo[0], relativo[1]
        gt_path = ground_truth_root / dataset / "ground_truth.yaml"
        if not gt_path.is_file():
            print(f"aviso: sem ground truth para '{dataset}', pulando", file=sys.stderr)
            continue
        indice = carregar_ground_truth(gt_path)
        chave_modelo = f"{dataset}/{modelo}"

        for linha in jsonl.read_text(encoding="utf-8").splitlines():
            if not linha.strip():
                continue
            registro = json.loads(linha)
            item = indice.get(registro.get("issue_id"))
            if item is None:
                continue
            valores = list(registro.get("top_values") or [])
            aceitos = item.all_accepted_values()

            antes1 = bool(registro.get("match_top1"))
            antes3 = bool(registro.get("match_top3"))
            depois1 = _casa(registro, aceitos, valores[:1])
            depois3 = _casa(registro, aceitos, valores[:3])

            estrato = registro.get("stratum") or "?"
            for alvo, chave in ((por_modelo, chave_modelo), (por_estrato, estrato)):
                acumulador = alvo[chave]
                acumulador.total += 1
                acumulador.top1_antes += antes1
                acumulador.top1_depois += depois1
                acumulador.top3_antes += antes3
                acumulador.top3_depois += depois3
                if antes1 != depois1 and len(acumulador.mudaram) < 5:
                    acumulador.mudaram.append(str(registro.get("issue_id")))

    return por_modelo, por_estrato


def _imprimir(titulo: str, tabela: dict[str, Tally]) -> None:
    print(f"\n=== {titulo} ===")
    print(
        f"{'chave':<34}{'n':>7}{'top1 antes':>12}{'top1 depois':>13}"
        f"{'delta pp':>10}{'top3 delta':>12}"
    )
    ordenado = sorted(
        tabela.items(),
        key=lambda par: par[1].taxa(par[1].top1_depois) - par[1].taxa(par[1].top1_antes),
        reverse=True,
    )
    for chave, t in ordenado:
        d1 = (t.taxa(t.top1_depois) - t.taxa(t.top1_antes)) * 100
        d3 = (t.taxa(t.top3_depois) - t.taxa(t.top3_antes)) * 100
        marca = "  <-" if abs(d1) > 0.05 or abs(d3) > 0.05 else ""
        print(
            f"{chave:<34}{t.total:>7}{t.taxa(t.top1_antes):>12.4f}"
            f"{t.taxa(t.top1_depois):>13.4f}{d1:>+10.2f}{d3:>+12.2f}{marca}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_root", type=Path, help="Raiz com <dataset>/<modelo>/run_*.jsonl")
    parser.add_argument(
        "--ground-truth-root",
        type=Path,
        default=PROJECT_ROOT / "data" / "evaluation",
        help="Diretório com <dataset>/ground_truth.yaml",
    )
    parser.add_argument("--json", type=Path, default=None, help="Grava o resultado como JSON")
    args = parser.parse_args()

    por_modelo, por_estrato = repontuar(args.results_root, args.ground_truth_root)
    if not por_modelo:
        print("nenhuma coleta encontrada", file=sys.stderr)
        raise SystemExit(1)

    _imprimir("Por modelo", por_modelo)
    _imprimir("Por estrato", por_estrato)

    if args.json:
        payload = {
            escopo: {
                chave: {
                    "total": t.total,
                    "top1_antes": t.top1_antes,
                    "top1_depois": t.top1_depois,
                    "top3_antes": t.top3_antes,
                    "top3_depois": t.top3_depois,
                    "exemplos_alterados": t.mudaram,
                }
                for chave, t in tabela.items()
            }
            for escopo, tabela in (("por_modelo", por_modelo), ("por_estrato", por_estrato))
        }
        args.json.write_text(
            json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print(f"\nJSON gravado em {args.json}")


if __name__ == "__main__":
    main()
