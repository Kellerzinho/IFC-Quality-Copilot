import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_runtime_dependencies_and_python_are_pinned():
    assert (ROOT / ".python-version").read_text(encoding="utf-8").strip() == "3.12.13"
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    names = {
        value.split("[", 1)[0].split(">", 1)[0].split("=", 1)[0].lower()
        for value in project["project"]["dependencies"]
    }
    assert {"pandas", "pyyaml", "psutil"} <= names
    assert {"pytest", "pytest-cov", "ruff", "mypy"} <= {
        value.split("[", 1)[0].split(">", 1)[0].split("=", 1)[0].lower()
        for value in project["dependency-groups"]["dev"]
    }
    assert (ROOT / "uv.lock").is_file()
