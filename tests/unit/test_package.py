"""Packaging checks: `src/` is installed as the `agentguard` package."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

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


def test_try_parses_json_and_quoted_values() -> None:
    tool, args = cli.parse_call(
        'push_files owner=o branch=fix/x files=[{"path":"README.md"}] body="two words" n=7'
    )
    assert tool == "push_files"
    assert args == {
        "owner": "o",
        "branch": "fix/x",
        "files": [{"path": "README.md"}],
        "body": "two words",
        "n": 7,
    }
    _, args = cli.parse_call("""t files='[{"path": "a b"}]'""")
    assert args == {"files": [{"path": "a b"}]}


def test_tool_list_survives_older_protocol_versions() -> None:
    """GitHub's tools declare output schemas like `"type": ["object", "null"]`; agents on
    MCP 2025-11-25 only accept `"type": "object"`, so the gateway must drop the others."""
    import mcp_types as types
    from mcp_types.methods import serialize_server_result

    from agentguard.proxy.upstream import Route, Upstreams

    schemas: list[dict[str, Any] | None] = [
        {"type": ["object", "null"]},
        {"oneOf": [{"type": "object"}, {"type": "null"}]},
        {"type": "object", "properties": {"sha": {"type": "string"}}},
        None,
    ]
    up = Upstreams([])
    for i, schema in enumerate(schemas):
        spec = types.Tool(name=f"t{i}", input_schema={"type": "object"}, output_schema=schema)
        up.routes[f"t{i}"] = Route("github", f"t{i}", spec)
    tools = up.tools()
    assert [t.output_schema for t in tools] == [None, None, schemas[2], None]
    dumped = types.ListToolsResult(tools=tools).model_dump(
        by_alias=True, mode="json", exclude_none=True
    )
    for version in ("2025-11-25", "2026-07-28"):
        serialize_server_result("tools/list", version, dumped)
