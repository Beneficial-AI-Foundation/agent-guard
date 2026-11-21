"""Editing an agent's MCP config: add AgentGuard, set aside direct copies of the
servers it guards (so the agent can't go around it), and keep a backup."""

from __future__ import annotations

import json
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..profile.mcp_json import ServerConfig, parse, strip_jsonc

ENTRY = "agentguard"


def agentguard_entry(profile_dir: Path) -> dict[str, Any]:
    exe = shutil.which("agentguard")
    if exe:
        return {"type": "stdio", "command": exe, "args": ["stdio", "--profile", str(profile_dir)]}
    return {
        "type": "stdio",
        "command": sys.executable,
        "args": ["-m", "agentguard", "stdio", "--profile", str(profile_dir)],
    }


def is_direct(raw: dict[str, Any], guarded: list[ServerConfig]) -> bool:
    """The entry reaches a server AgentGuard guards without going through it."""
    for s in guarded:
        if s.url and raw.get("url") and str(raw["url"]).rstrip("/") == s.url.rstrip("/"):
            return True
        if s.command and raw.get("command") == s.command and list(raw.get("args", [])) == s.args:
            return True
    return False


@dataclass
class ConfigFile:
    """An mcp.json-style file: `servers` (VS Code) or `mcpServers` (Claude, Cursor)."""

    path: Path
    key: str
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def read(cls, path: Path, key: str) -> ConfigFile:
        if not path.exists():
            return cls(path, key, {key: {}})
        text = path.read_text(encoding="utf-8")
        data = json.loads(strip_jsonc(text)) if text.strip() else {}
        data.setdefault(key, {})
        return cls(path, key, data)

    @property
    def servers(self) -> dict[str, Any]:
        servers: dict[str, Any] = self.data[self.key]
        return servers

    def has_agentguard(self) -> bool:
        return any(
            name == ENTRY
            or "agentguard"
            in " ".join([str(v.get("command", ""))] + [str(a) for a in v.get("args", [])])
            for name, v in self.servers.items()
        )

    def direct(self, guarded: list[ServerConfig]) -> list[str]:
        return [n for n, v in self.servers.items() if n != ENTRY and is_direct(v, guarded)]

    def connect(
        self, profile_dir: Path, guarded: list[ServerConfig]
    ) -> tuple[list[str], Path | None]:
        """Adds AgentGuard and moves direct entries out. Returns (moved, backup)."""
        backup = None
        if self.path.exists():
            backup = self.path.with_name(f"{self.path.name}.agentguard-backup-{int(time.time())}")
            shutil.copy2(self.path, backup)
        moved = self.direct(guarded)
        aside = self.data.setdefault("agentguardDisabled", {})
        for name in moved:
            aside[name] = self.servers.pop(name)
        self.servers[ENTRY] = agentguard_entry(profile_dir)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2) + "\n", encoding="utf-8")
        return moved, backup


def parse_servers(path: Path) -> dict[str, Any]:
    return parse(path.read_text(encoding="utf-8")) if path.exists() else {}
