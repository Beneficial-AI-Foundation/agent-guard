"""Phase 0 checks: `src/` is installed as the `agentguard` package."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import agentguard
from agentguard import cli

REPO = Path(__file__).resolve().parents[2]


def test_package_is_the_src_folder() -> None:
    assert Path(agentguard.__file__).resolve().parent == REPO / "src"


def test_version_is_known() -> None:
    assert agentguard.__version__ != "0.0.0+unknown"


def test_version_command(capsys: pytest.CaptureFixture[str], worker_binary: Path) -> None:
    assert cli.main(["version"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == f"agentguard {agentguard.__version__}"
    assert out[1].startswith("guard-worker ") and "no_exfiltration" in out[2]


def test_python_dash_m() -> None:
    out = subprocess.run(
        [sys.executable, "-m", "agentguard", "version"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert out.startswith("agentguard ")


def test_no_inner_agentguard_folder() -> None:
    assert not (REPO / "src" / "agentguard").exists()


def test_every_subpackage_is_listed_in_pyproject() -> None:
    """setuptools only ships packages listed in pyproject.toml; catch omissions."""
    import tomllib

    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text())
    listed = set(pyproject["tool"]["setuptools"]["packages"])
    src = REPO / "src"
    found = {"agentguard"} | {
        "agentguard." + ".".join(d.relative_to(src).parts)
        for d in src.rglob("*")
        if d.is_dir()
        and any(d.glob("*.py"))
        and "__pycache__" not in d.parts
        and "templates" not in d.relative_to(src).parts  # package data, not code
    }
    assert found == listed
