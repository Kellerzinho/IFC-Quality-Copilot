"""Dump de prompts com cliente espião — zero LLM, zero GPU (~2 min).

Roda o harness real (ExperimentRunner.run_single) no dataset predio com
OllamaClient.generate substituído por um espião que grava (system, user)
por estímulo e devolve JSON vazio. Serve para diffar o instrumento antes e
depois de mudanças de código, sem rodar benchmark — foi assim que a revisão
bSDD de 2026-08-04 provou que os prompts v6 e v6.1 são byte-idênticos
(202/202 estímulos; ver docs/revisao-bsdd-2026-08-04.md).

Uso:
    python scripts/dump_prompts_spy.py <saida.json>

Compare dois dumps com scripts/diff_prompts.py.
"""

# ruff: noqa: E402 — o sys.path.insert precisa vir antes dos imports de src/.

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from loguru import logger

logger.remove()
logger.add(sys.stderr, level="WARNING")

from src.suggestion_engine.ollama_client import OllamaClient
from src.suggestion_engine.suggestion import SuggestionGenerator

# ---- espião -----------------------------------------------------------------
CAPTURED: list[dict] = []
_CURRENT_ISSUE: dict = {"id": None, "type": None, "prop": "", "calls": 0}

_original_generate_issue = SuggestionGenerator.generate


def _tracking_generate(self, issue, *args, **kwargs):
    """Anota qual issue está sendo processada para o espião de prompts."""
    _CURRENT_ISSUE["id"] = issue.id
    _CURRENT_ISSUE["type"] = issue.issue_type
    _CURRENT_ISSUE["prop"] = str(issue.context.get("check_property") or "")
    _CURRENT_ISSUE["calls"] = 0
    return _original_generate_issue(self, issue, *args, **kwargs)


def _spy_generate(self, prompt, system=None, temperature=None):
    """Captura o prompt no lugar de chamar o Ollama; devolve JSON vazio."""
    _CURRENT_ISSUE["calls"] += 1
    CAPTURED.append(
        {
            "issue_id": _CURRENT_ISSUE["id"],
            "issue_type": _CURRENT_ISSUE["type"],
            "check_property": _CURRENT_ISSUE["prop"],
            "attempt": _CURRENT_ISSUE["calls"],
            "system": system or "",
            "user": prompt,
        }
    )
    return '{"opcoes": []}', {}


def main() -> None:
    """Executa o harness com o espião e grava o dump JSON."""
    SuggestionGenerator.generate = _tracking_generate
    OllamaClient.generate = _spy_generate
    OllamaClient.warm_up = lambda self: True
    OllamaClient.is_available = lambda self: True

    from src.experiment.runner import ExperimentRunner

    eval_dir = PROJECT_ROOT / "data" / "evaluation" / "predio"
    building_context = {
        "building_type": "Residencial multifamiliar",
        "bioclimatic_zone": "3",
    }
    out_path = Path(sys.argv[1])

    runner = ExperimentRunner()
    runner.run_single(
        ifc_path=str(eval_dir / "predio_v1.ifc"),
        ground_truth_path=str(eval_dir / "ground_truth.yaml"),
        building_context=building_context,
        ids_path=str(PROJECT_ROOT / "data" / "ids_templates" / "residencial_nbr15575.ids"),
        model_name="spy-dump",
        cache_enabled=False,
        replica_index=0,
        issue_types=None,
        reuse_equivalent=True,
    )

    out_path.write_text(json.dumps(CAPTURED, ensure_ascii=False, indent=1), encoding="utf-8")
    primeiras = [c for c in CAPTURED if c["attempt"] == 1]
    logger.warning(
        "capturados: {} chamadas, {} estimulos -> {}", len(CAPTURED), len(primeiras), out_path
    )


if __name__ == "__main__":
    main()
