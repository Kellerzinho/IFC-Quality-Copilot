"""Compara dois logs do mypy preservando multiplicidade (E5, 27/10/2026).

Uso: compare_mypy_e5.py LOG_ATUAL LOG_HEAD SAIDA_JSON

Chave de cada diagnóstico ``error``: (caminho normalizado com ``/``, mensagem com
``[código]``), sem linha/coluna, contada com multiplicidade (``Counter``). Notas são
ignoradas. Diagnósticos acrescentados ou removidos aparecem com a contagem da diferença.
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

LINE = re.compile(r"^(?P<path>[^:]+(?::[\\/][^:]+)?):\d+(?::\d+)?: error: (?P<msg>.*)$")


def diagnostics(log: Path) -> Counter[tuple[str, str]]:
    found: Counter[tuple[str, str]] = Counter()
    for raw in log.read_text(encoding="utf-8", errors="replace").splitlines():
        match = LINE.match(raw.strip())
        if match:
            found[(match["path"].replace("\\", "/"), match["msg"].strip())] += 1
    return found


current, head = diagnostics(Path(sys.argv[1])), diagnostics(Path(sys.argv[2]))
added = current - head
removed = head - current
summary = {
    "current_errors": sum(current.values()),
    "current_files": len({path for path, _ in current}),
    "head_errors": sum(head.values()),
    "head_files": len({path for path, _ in head}),
    "added": [{"path": p, "message": m, "count": n} for (p, m), n in sorted(added.items())],
    "removed": [{"path": p, "message": m, "count": n} for (p, m), n in sorted(removed.items())],
}
Path(sys.argv[3]).write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
print(
    json.dumps(
        {k: v if not isinstance(v, list) else len(v) for k, v in summary.items()},
        ensure_ascii=False,
    )
)
