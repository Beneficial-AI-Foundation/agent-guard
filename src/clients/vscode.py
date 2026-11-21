"""VS Code: user-level mcp.json, or a workspace's .vscode/mcp.json ("servers")."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def user_config() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/Code/User/mcp.json"
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home())) / "Code/User/mcp.json"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "Code/User/mcp.json"


def workspace_config(folder: Path) -> Path:
    return folder / ".vscode" / "mcp.json"


KEY = "servers"
