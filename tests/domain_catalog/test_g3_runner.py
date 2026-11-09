"""Regressões do gate de evidência: erro/incompletude nunca retorna sucesso."""

import ctypes
import runpy
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize(
    ("outcome", "expected_exit"),
    [
        ("passed", 0),
        ("failed", 1),
        ("wrong_node", 1),
        ("ipv6", 0),
        ("class_param", 0),
        ("wrong_param", 1),
    ],
)
def test_partition_runner_creates_parent_and_propagates_gate_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
    expected_exit: int,
) -> None:
    runner = Path(__file__).resolve().parents[2] / "docs/catalogo/evidencias-e5/g3_partition_e5.py"
    evidence = tmp_path / "evidence"
    temp = tmp_path / "missing-parent" / "temp"

    def memory(pointer: object) -> int:
        pointer._obj.ullAvailPhys = 3 * 1024**3  # type: ignore[attr-defined]
        return 1

    monkeypatch.setattr(
        ctypes,
        "windll",
        SimpleNamespace(kernel32=SimpleNamespace(GlobalMemoryStatusEx=memory)),
        raising=False,
    )

    node = "tests/fake.py::test_one"
    classname = "tests.fake"
    case_name = "test_one"
    if outcome in ("ipv6", "wrong_param"):
        node = "tests/fake.py::test_one[http://[::1]:8000]"
        case_name = "test_one[http://[::1]:8000]"
    if outcome == "class_param":
        node = "tests/fake.py::TestClass::test_one[a::b]"
        classname = "tests.fake.TestClass"
        case_name = "test_one[a::b]"
    if outcome == "wrong_param":
        case_name = "test_one[http://[::2]:8000]"

    def run(args: list[str], **kwargs: object) -> SimpleNamespace:
        if "--collect-only" in args:
            return SimpleNamespace(stdout=node + "\n", returncode=0)
        assert temp.is_dir()
        junit = Path(next(a.split("=", 1)[1] for a in args if a.startswith("--junitxml=")))
        name = "test_other" if outcome == "wrong_node" else case_name
        error = '<failure message="synthetic" />' if outcome == "failed" else ""
        junit.write_text(
            "<testsuites><testsuite>"
            f'<testcase classname="{classname}" name="{name}">{error}</testcase>'
            "</testsuite></testsuites>",
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=1 if outcome == "failed" else 0)

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(sys, "argv", [str(runner), sys.executable, str(evidence), str(temp)])
    with pytest.raises(SystemExit) as result:
        runpy.run_path(str(runner), run_name="__main__")
    assert result.value.code == expected_exit
