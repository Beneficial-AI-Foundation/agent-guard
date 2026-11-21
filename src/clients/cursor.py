"""Cursor: ~/.cursor/mcp.json, or a project's .cursor/mcp.json ("mcpServers")."""

from __future__ import annotations

from pathlib import Path


def user_config() -> Path:
    return Path.home() / ".cursor" / "mcp.json"


def workspace_config(folder: Path) -> Path:
    return folder / ".cursor" / "mcp.json"


KEY = "mcpServers"
