"""Errors AgentGuard reports to people (not to agents)."""

from __future__ import annotations


class AgentGuardError(Exception):
    """Base class: the message is shown to the user as is."""


class ProfileError(AgentGuardError):
    """A profile folder (mcp.json, rules.yaml, .env) can't be used."""


class RulesError(AgentGuardError):
    """A rule file is invalid. `problems` lists every problem found."""

    def __init__(self, message: str, problems: list[str] | None = None) -> None:
        self.problems = problems or []
        detail = "".join(f"\n  - {p}" for p in self.problems)
        super().__init__(message + detail)


class WorkerError(AgentGuardError):
    """The Lean decision worker failed. The gateway treats this as deny."""


class AuthError(AgentGuardError):
    """Signing in to an upstream server failed."""
