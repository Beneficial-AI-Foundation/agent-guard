"""Where AgentGuard keeps things, and settings read from AGENTGUARD_* variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class Mode(StrEnum):
    """`off`: forward unchecked. `audit`: decide and log, but forward everything.
    `enforce`: apply the verdict."""

    OFF = "off"
    AUDIT = "audit"
    ENFORCE = "enforce"


def home() -> Path:
    """`~/.agentguard`, or `AGENTGUARD_HOME`."""
    return Path(os.environ.get("AGENTGUARD_HOME", "~/.agentguard")).expanduser()


def default_profile(name: str = "github") -> Path:
    return home() / name


@dataclass(frozen=True)
class Settings:
    mode: Mode = Mode.ENFORCE
    gateway_host: str = "127.0.0.1"
    gateway_port: int = 8080
    console_port: int = 7070
    #: The console only answers loopback Host headers.
    console_host: str = "127.0.0.1"
    #: Seconds a person has to answer an `ask` before it counts as rejected.
    approval_timeout: float = 300.0
    #: Seconds the Lean worker has to answer before the call is denied.
    worker_timeout: float = 5.0

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ
        return cls(
            mode=Mode(env.get("AGENTGUARD_MODE", Mode.ENFORCE)),
            gateway_host=env.get("AGENTGUARD_HOST", "127.0.0.1"),
            gateway_port=int(env.get("AGENTGUARD_PORT", "8080")),
            console_port=int(env.get("AGENTGUARD_CONSOLE_PORT", "7070")),
            console_host=env.get("AGENTGUARD_CONSOLE_HOST", "127.0.0.1"),
            approval_timeout=float(env.get("AGENTGUARD_APPROVAL_TIMEOUT", "300")),
            worker_timeout=float(env.get("AGENTGUARD_WORKER_TIMEOUT", "5")),
        )
