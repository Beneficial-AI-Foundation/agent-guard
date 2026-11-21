"""One state per agent session: what Lean needs (level, tainted) plus what the console shows."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field

from ..monitor.worker import SessionState


@dataclass
class AgentSession:
    key: str
    state: SessionState = field(default_factory=SessionState)
    started: float = field(default_factory=time.time)
    calls: int = 0
    #: The last few results that contained outsider text.
    outsider_text: deque[str] = field(default_factory=lambda: deque(maxlen=3))
    #: Calls in one session are decided one at a time, so the state can't race.
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    def to_json(self) -> dict[str, object]:
        return {
            "key": self.key,
            "level": self.state.level,
            "tainted": self.state.tainted,
            "started": self.started,
            "calls": self.calls,
        }


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, AgentSession] = {}

    def get(self, key: str) -> AgentSession:
        if key not in self._sessions:
            self._sessions[key] = AgentSession(key)
        return self._sessions[key]

    def end(self, key: str) -> bool:
        """Drops a session; its next call starts from a fresh state."""
        s = self._sessions.get(key)
        if s is None or s.lock.locked():
            return False
        del self._sessions[key]
        return True

    def all(self) -> list[AgentSession]:
        return list(self._sessions.values())
