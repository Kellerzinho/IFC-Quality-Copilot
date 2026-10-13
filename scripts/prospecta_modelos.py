"""Inventário de hardware e tabela de prospecção de modelos (tarefa M7-09).

Somente leitura: coleta GPU/VRAM, CUDA, RAM, disco, SO e metadados do Ollama
(``--version``, ``list``, ``show``), estima a memória de cada candidato e grava
em ``research/M7/prospection/``:

- ``hardware-profiles.json`` — perfil desta máquina + laboratório não confirmado;
- ``models.jsonl`` — um ``ModelProspectionRecord`` por modelo × quantização;
- ``prospeccao.md`` — leitura gerada a partir dos dois arquivos acima.

Não carrega, baixa nem testa modelo, e não inicia o servidor do Ollama.

Uso:

    uv run python scripts/prospecta_modelos.py
    uv run python scripts/prospecta_modelos.py --sem-coleta   # só recalcula/renderiza
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.experiment.budget_v1.prospection import (  # noqa: E402
    DEFAULT_RAM_RESERVE_GIB,
    DEFAULT_RUNTIME_RESERVE_GIB,
    MARKDOWN_FILE,
    PROSPECTION_DIR,
    build_records,
    collect_hardware_profile,
    load_outputs,
    redact_profile,
    render_markdown,
    unconfirmed_profile,
    write_outputs,
)
from src.experiment.budget_v1.prospection_sources import CANDIDATES  # noqa: E402

LAB_PROFILE_ID = "ime-se2-lab"
LAB_NOTE = (
    "Laboratório da SE2 (linha IME): GPU, VRAM, RAM, acesso e concorrência ainda não "
    "confirmados. Toda célula fica condicionada até haver inventário real (T7-26)."
)


def main(argv: list[str] | None = None) -> int:
    """Coleta (ou relê) o perfil, gera os registros e escreve as três saídas."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--saida", type=Path, default=PROJECT_ROOT / PROSPECTION_DIR)
    parser.add_argument(
        "--sem-coleta",
        action="store_true",
        help="reaproveita o perfil pessoal já gravado em hardware-profiles.json",
    )
    parser.add_argument("--reserva-runtime-gib", type=float, default=DEFAULT_RUNTIME_RESERVE_GIB)
    parser.add_argument("--reserva-ram-gib", type=float, default=DEFAULT_RAM_RESERVE_GIB)
    args = parser.parse_args(argv)

    if args.sem_coleta:
        profiles, _ = load_outputs(args.saida)
        personal = next(p for p in profiles if p.line == "pessoal")
    else:
        personal = redact_profile(
            collect_hardware_profile(
                project_root=PROJECT_ROOT,
                collected_on=datetime.now(UTC).date().isoformat(),
            )
        )
    profiles = [personal, unconfirmed_profile(LAB_PROFILE_ID, LAB_NOTE)]

    records = build_records(
        CANDIDATES,
        profiles,
        runtime_reserve_gib=args.reserva_runtime_gib,
        ram_reserve_gib=args.reserva_ram_gib,
    )
    write_outputs(args.saida, profiles, records)
    profiles, records = load_outputs(args.saida)
    (args.saida / MARKDOWN_FILE).write_text(
        render_markdown(profiles, records), encoding="utf-8", newline="\n"
    )
    logger.info("{} registros gravados em {}", len(records), args.saida.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
