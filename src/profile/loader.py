"""A profile folder: `mcp.json` (the servers), `rules.yaml` (the rules), `.env` (secrets)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..errors import ProfileError
from . import mcp_json, rules
from .env import load_dotenv
from .mcp_json import ServerConfig


@dataclass(frozen=True)
class Profile:
    folder: Path
    servers: list[ServerConfig]
    policy: dict[str, Any]
    policy_hash: str

    @property
    def name(self) -> str:
        return self.folder.name

    @property
    def rules_path(self) -> Path:
        return self.folder / "rules.yaml"

    def server(self, name: str) -> ServerConfig:
        for s in self.servers:
            if s.name == name:
                return s
        raise ProfileError(f"no server named {name!r} in {self.folder / 'mcp.json'}")


def load(folder: Path) -> Profile:
    folder = folder.expanduser().resolve()
    if not folder.is_dir():
        raise ProfileError(f"profile folder {folder} not found (create one with `agentguard init`)")
    # .env wins over the process environment, so a profile is self-contained.
    env = dict(os.environ) | load_dotenv(folder / ".env")
    servers = mcp_json.load(folder / "mcp.json", env)
    policy = rules.load(folder / "rules.yaml")
    return Profile(folder, servers, policy, rules.policy_hash(policy))
