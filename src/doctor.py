"""`agentguard doctor`: checks that AgentGuard works and that nothing goes around it."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .clients import claude_code, cursor, vscode
from .clients.base import ConfigFile
from .profile.loader import Profile

#: Credentials in the environment that let an agent with a shell skip any gateway.
SHELL_TOKENS = ("GITHUB_TOKEN", "GH_TOKEN", "GITHUB_PERSONAL_ACCESS_TOKEN")


@dataclass
class Finding:
    level: str  # ok, warn, fail
    text: str

    @property
    def mark(self) -> str:
        return {"ok": "✓", "warn": "⚠", "fail": "✗"}[self.level]


def client_configs(cwd: Path) -> list[tuple[str, ConfigFile]]:
    out = []
    for label, mod in (("VS Code", vscode), ("Cursor", cursor), ("Claude Code", claude_code)):
        for scope, path in (("user", mod.user_config()), ("project", mod.workspace_config(cwd))):
            if path.exists():
                try:
                    out.append((f"{label} ({scope}) {path}", ConfigFile.read(path, mod.KEY)))
                except ValueError:
                    continue
    return out


def check_clients(profile: Profile, cwd: Path) -> list[Finding]:
    found = []
    configs = client_configs(cwd)
    if not configs:
        return [Finding("warn", "no agent MCP config found; run `agentguard connect <client>`")]
    for where, cfg in configs:
        direct = cfg.direct(profile.servers)
        if direct:
            found.append(
                Finding(
                    "fail",
                    f"{where}: {', '.join(direct)} reaches a guarded "
                    "server directly; run `agentguard connect`",
                )
            )
        elif cfg.has_agentguard():
            found.append(Finding("ok", f"{where}: uses AgentGuard"))
    return found


def check_shell() -> list[Finding]:
    found = []
    for var in SHELL_TOKENS:
        if os.environ.get(var):
            found.append(
                Finding(
                    "warn",
                    f"{var} is set: an agent with a shell could use it "
                    "directly, without AgentGuard",
                )
            )
    gh = shutil.which("gh")
    if gh:
        signed_in = subprocess.run([gh, "auth", "status"], capture_output=True).returncode == 0  # noqa: S603
        if signed_in:
            found.append(
                Finding(
                    "warn",
                    "the gh CLI is signed in: an agent with a shell could "
                    "use it directly, without AgentGuard",
                )
            )
    return found
