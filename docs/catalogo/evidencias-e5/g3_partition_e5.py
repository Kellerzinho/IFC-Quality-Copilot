"""G3 particionada E5: coleta completa, grupos disjuntos pequenos, execução sequencial.

Uso: g3_partition_e5.py PYTHON PASTA_EVIDENCIA PASTA_TEMP [MIN_MB_LIVRES]

1. Coleta ``tests -m "not network and not windows_e2e"`` (conjunto esperado), gravada antes
   de qualquer execução, e a coleta sem marcador (para listar as deseleções por nome).
2. Particiona por arquivo em grupos disjuntos de até ``MAX_NODES`` nós; ``tests/experiment``
   vai arquivo a arquivo (foi onde a G3 de 23/10 esgotou a memória).
3. Antes de cada grupo confere a memória física livre; abaixo do mínimo **para** e registra
   o grupo como não iniciado (não espera nem reinicia sozinho). Cada execução é nova;
   não reaproveita resultados históricos apenas porque os nodeids coincidem.
4. Cada grupo: coleta própria (nodeids) + execução com JUnit, um processo por vez.
5. Confere união dos nodeids == esperado, sem duplicata/omissão, e testcases do JUnit ==
   coletados do grupo. Interrompido ou ausente nunca conta como passe.
"""

import ctypes
import hashlib
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

python, evidence, temp = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
MIN_FREE_MB = int(sys.argv[4]) if len(sys.argv) > 4 else 1200
MAX_NODES = 160
MARK = "not network and not windows_e2e"
BASE = [python, "-B", "-m", "pytest", "-p", "no:cacheprovider"]
env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"}
evidence.mkdir(parents=True, exist_ok=True)
temp.mkdir(parents=True, exist_ok=True)
env["TEMP"] = env["TMP"] = str(temp)


class _Memory(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def free_mb() -> int:
    status = _Memory()
    status.dwLength = ctypes.sizeof(_Memory)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))  # type: ignore[attr-defined]
    return int(status.ullAvailPhys // (1024 * 1024))


def collect(paths: list[str], marker: str | None = MARK) -> list[str]:
    args = [*BASE, *(["-m", marker] if marker else []), "--collect-only", "-q", *paths]
    out = subprocess.run(
        args, capture_output=True, text=True, encoding="utf-8", env=env, check=True
    ).stdout
    return [line.strip() for line in out.splitlines() if "::" in line]


expected = collect(["tests"])
everything = collect(["tests"], marker=None)
expected_text = "\n".join(sorted(expected)) + "\n"
(evidence / "g3-expected-nodes.txt").write_text(expected_text, encoding="utf-8")
expected_sha = hashlib.sha256(expected_text.encode()).hexdigest()

per_file = Counter(node.split("::")[0] for node in expected)
groups: dict[str, list[str]] = {}
current: list[str] = []
size = 0
index = 0


def folder_of(name: str) -> str:
    return name.split("/")[1] if name.count("/") > 1 else "raiz"


for name in sorted(per_file):
    folder = folder_of(name)
    if folder == "experiment":
        groups[f"exp-{Path(name).stem}"] = [name]
        continue
    if current and (size + per_file[name] > MAX_NODES or folder_of(current[0]) != folder):
        groups[f"g{index:02d}"] = current
        index += 1
        current, size = [], 0
    current.append(name)
    size += per_file[name]
if current:
    groups[f"g{index:02d}"] = current
assert sorted(f for g in groups.values() for f in g) == sorted(per_file)

result_path = evidence / "g3-result.json"

summary: dict = {
    "start_utc": datetime.now(UTC).isoformat(),
    "python": python,
    "marker": MARK,
    "expected_nodes": len(expected),
    "expected_sha256": expected_sha,
    "expected_duplicates": [k for k, v in Counter(expected).items() if v > 1],
    "collected_without_marker": len(everything),
    "deselected_by_marker": sorted(set(everything) - set(expected)),
    "min_free_mb": MIN_FREE_MB,
    "max_nodes_per_group": MAX_NODES,
    "groups": {},
}
seen: list[str] = []
stopped = None
for key, paths in groups.items():
    if stopped is not None:
        summary["groups"][key] = {"files": paths, "status": "not_started", "reason": stopped}
        continue
    available = free_mb()
    if available < MIN_FREE_MB:
        stopped = f"memória livre {available} MB < {MIN_FREE_MB} MB antes do grupo {key}"
        summary["groups"][key] = {"files": paths, "status": "not_started", "reason": stopped}
        continue
    nodes = collect(paths)
    seen.extend(nodes)
    junit = evidence / f"g3-{key}-junit.xml"
    start = datetime.now(UTC).isoformat()
    with (evidence / f"g3-{key}.log").open("wb") as log:
        proc = subprocess.run(
            [*BASE, "-m", MARK, "-q", f"--basetemp={temp / key}", f"--junitxml={junit}", *paths],
            stdout=log,
            stderr=subprocess.STDOUT,
            env=env,
            check=False,
        )
    cases = ET.parse(junit).getroot().findall(".//testcase") if junit.exists() else []
    counts = Counter(
        "failed"
        if c.find("failure") is not None
        else "error"
        if c.find("error") is not None
        else "skipped"
        if c.find("skipped") is not None
        else "passed"
        for c in cases
    )
    skips = [
        {
            "case": f"{c.get('classname')}::{c.get('name')}",
            "message": c.find("skipped").get("message"),
        }  # type: ignore[union-attr]
        for c in cases
        if c.find("skipped") is not None
    ]

    def junit_identity(node: str) -> tuple[str, str]:
        # Parameter IDs may themselves contain :: (e.g. IPv6 URLs).
        path, bracket, params = node.partition("[")
        names = path.split("::")
        names[0] = names[0].replace("/", ".").removesuffix(".py")
        names[-1] += bracket + params
        return ".".join(names[:-1]), names[-1]

    expected_cases = Counter(junit_identity(node) for node in nodes)
    actual_cases = Counter((c.get("classname"), c.get("name")) for c in cases)
    complete = junit.exists() and actual_cases == expected_cases
    summary["groups"][key] = {
        "files": paths,
        "nodes": nodes,
        "collected": len(nodes),
        "junit_testcases": len(cases),
        "junit_matches_collected": complete,
        "command": [
            *BASE,
            "-m",
            MARK,
            "-q",
            f"--basetemp={temp / key}",
            f"--junitxml={junit}",
            *paths,
        ],
        "counts": dict(counts),
        "skips": skips,
        "exit_code": proc.returncode,
        "status": "completed" if complete and proc.returncode == 0 else "failed_or_incomplete",
        "free_mb_before": available,
        "start_utc": start,
        "end_utc": datetime.now(UTC).isoformat(),
    }
    print(key, len(nodes), dict(counts), proc.returncode, available, flush=True)
    result_path.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")

totals: Counter = Counter()
for group in summary["groups"].values():
    totals.update(group.get("counts", {}))
statuses = Counter(group["status"] for group in summary["groups"].values())
dup = [k for k, v in Counter(seen).items() if v > 1]
summary.update(
    {
        "end_utc": datetime.now(UTC).isoformat(),
        "union_equals_expected": sorted(set(seen)) == sorted(expected) and not dup,
        "union_nodes": len(seen),
        "duplicates_across_groups": dup,
        "missing": sorted(set(expected) - set(seen)),
        "extra": sorted(set(seen) - set(expected)),
        "totals": dict(totals),
        "group_status": dict(statuses),
        "stopped": stopped,
        "status": "COMPLETE"
        if statuses == Counter({"completed": len(groups)}) and sorted(seen) == sorted(expected)
        else "INCOMPLETE — não equivale a passe",
    }
)
result_path.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
print(
    json.dumps(
        {k: v for k, v in summary.items() if k not in ("groups", "deselected_by_marker")},
        ensure_ascii=False,
    )
)

raise SystemExit(0 if summary["status"] == "COMPLETE" else 1)
