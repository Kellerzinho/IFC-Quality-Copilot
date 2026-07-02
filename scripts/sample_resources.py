"""Amostragem externa de VRAM/RAM durante os runs do benchmark (Fase B.3).

Mede recursos POR FORA do processo do experimento (como o plano pede): a cada
intervalo, consulta ``nvidia-smi`` (VRAM usada) e a memória do sistema, e
acrescenta uma linha com timestamp ISO a um CSV. A correlação com os runs é
feita por timestamp contra os ``run_*.json``.

Uso (num terminal separado, antes de iniciar o benchmark):

    python scripts/sample_resources.py --output resources.csv --interval 1

Encerra com Ctrl+C (o CSV fica válido a cada linha) ou com --duration N segundos.
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


def _vram_used_mb() -> float | None:
    """VRAM usada (MB) via nvidia-smi; None se a consulta falhar."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode != 0:
            return None
        return float(out.stdout.strip().splitlines()[0])
    except Exception:
        return None


def _ram_used_mb() -> float | None:
    """RAM usada (MB) via psutil; None se psutil não estiver disponível."""
    try:
        import psutil
    except ImportError:
        return None
    vm = psutil.virtual_memory()
    return round((vm.total - vm.available) / (1024 * 1024), 1)


def main(argv: list[str] | None = None) -> int:
    """Loop de amostragem até Ctrl+C ou --duration."""
    parser = argparse.ArgumentParser(
        prog="python scripts/sample_resources.py",
        description="Amostra VRAM (nvidia-smi) e RAM (psutil) em CSV com timestamp.",
    )
    parser.add_argument("--output", required=True, help="Caminho do CSV de saída (append)")
    parser.add_argument("--interval", type=float, default=1.0, help="Segundos entre amostras")
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Duração total em segundos (default: até Ctrl+C)",
    )
    args = parser.parse_args(argv)

    if _ram_used_mb() is None:
        print("AVISO: psutil indisponível — coluna ram_used_mb ficará vazia", file=sys.stderr)
    if _vram_used_mb() is None:
        print("AVISO: nvidia-smi indisponível — coluna vram_used_mb ficará vazia", file=sys.stderr)

    output = Path(args.output)
    new_file = not output.exists()
    t_end = time.monotonic() + args.duration if args.duration else None

    with output.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        if new_file:
            writer.writerow(["timestamp", "vram_used_mb", "ram_used_mb"])
        try:
            while t_end is None or time.monotonic() < t_end:
                writer.writerow(
                    [datetime.now().isoformat(timespec="seconds"), _vram_used_mb(), _ram_used_mb()]
                )
                fh.flush()
                time.sleep(args.interval)
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
