"""Claude Code: a project's .mcp.json, or user scope through the `claude` CLI
(its user config, ~/.claude.json, holds much more than MCP servers, so AgentGuard
doesn't edit it directly)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

KEY = "mcpServers"


def user_config() -> Path:
    return Path.home() / ".claude.json"


def workspace_config(folder: Path) -> Path:
    return folder / ".mcp.json"


def cli() -> str | None:
    return shutil.which("claude")


def add_user(entry: dict[str, Any]) -> None:
    exe = cli()
    assert exe is not None
    subprocess.run(  # noqa: S603
        [exe, "mcp", "add-json", "-s", "user", "agentguard", json.dumps(entry)], check=True
    )


def remove_user(name: str) -> None:
    exe = cli()
    assert exe is not None
    subprocess.run([exe, "mcp", "remove", "-s", "user", name], check=True)  # noqa: S603
