"""Client for the Lean decision worker (`guard-worker`).

Every verdict comes from Lean. This module only moves JSON lines, and turns every
failure (timeout, crash, malformed reply) into **deny**. A crashed worker is
restarted with the current rules.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from ..errors import RulesError, WorkerError

Verdict = Literal["allow", "ask", "deny"]

#: A tool call's arguments can be large (file contents); allow long lines.
_LINE_LIMIT = 64 * 1024 * 1024


@dataclass(frozen=True)
class SessionState:
    """What the agent has seen: highest label read, and whether it read outsider text."""

    level: int = 0
    tainted: bool = False

    def to_json(self) -> dict[str, Any]:
        return {"level": self.level, "tainted": self.tainted}

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> SessionState:
        return cls(level=int(d["level"]), tainted=bool(d["tainted"]))


@dataclass(frozen=True)
class Decision:
    verdict: Verdict
    #: rule, no_rule, leak, untrusted, allowed, or error
    cause: str
    #: 1-based position of the deciding rule, if any.
    rule: int | None
    theorem: str | None
    #: The session if the call runs.
    next: SessionState
    read_level: int = 0
    dests: list[int] = field(default_factory=list)
    untrusted: bool = True
    high_impact: bool = True
    error: str | None = None

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> Decision:
        verdict = d["verdict"]
        if verdict not in ("allow", "ask", "deny"):
            raise WorkerError(f"unexpected verdict {verdict!r}")
        k = d["class"]
        return cls(
            verdict=verdict,
            cause=str(d["cause"]),
            rule=d.get("rule"),
            theorem=d.get("theorem"),
            next=SessionState.from_json(d["next"]),
            read_level=int(k["readLevel"]),
            dests=[int(x) for x in k["dests"]],
            untrusted=bool(k["untrusted"]),
            high_impact=bool(k["highImpact"]),
        )

    @classmethod
    def deny_on_error(cls, message: str, session: SessionState) -> Decision:
        return cls("deny", "error", None, None, session, error=message)


def find_binary() -> Path:
    """`AGENTGUARD_WORKER`, the binary shipped in the wheel, or a dev build in `lean/`."""
    if env := os.environ.get("AGENTGUARD_WORKER"):
        return Path(env)
    exe = "guard-worker.exe" if sys.platform == "win32" else "guard-worker"
    here = Path(__file__).resolve().parent.parent
    for candidate in (here / "bin" / exe, here.parent / "lean" / ".lake" / "build" / "bin" / exe):
        if candidate.exists():
            return candidate
    raise WorkerError(
        "guard-worker not found: install a wheel that includes it, build it with "
        "`make proofs`, or set AGENTGUARD_WORKER"
    )


class Worker:
    """One `guard-worker` process. Calls are serialised; each takes well under 1 ms."""

    def __init__(self, binary: Path | None = None, timeout: float = 5.0) -> None:
        self.binary = binary or find_binary()
        self.timeout = timeout
        self.policy: dict[str, Any] | None = None
        self._proc: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()
        self._next_id = 0

    async def __aenter__(self) -> Worker:
        await self._spawn()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def _spawn(self) -> None:
        self._proc = await asyncio.create_subprocess_exec(
            str(self.binary),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            limit=_LINE_LIMIT,
        )

    async def close(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        if proc.stdin:
            proc.stdin.close()
        try:
            await asyncio.wait_for(proc.wait(), 2)
        except TimeoutError:
            proc.kill()
            await proc.wait()

    async def _restart(self) -> None:
        proc, self._proc = self._proc, None
        if proc is not None and proc.returncode is None:
            proc.kill()
            with contextlib.suppress(Exception):
                await proc.wait()
        await self._spawn()
        if self.policy is not None:
            reply = await self._send({"op": "load", "policy": self.policy})
            if not reply.get("ok"):
                raise WorkerError("worker restarted but rejected the current rules")

    async def _send(self, req: dict[str, Any]) -> dict[str, Any]:
        """One request and its reply. Caller holds the lock."""
        if self._proc is None:
            await self._spawn()
        proc = self._proc
        assert proc is not None and proc.stdin is not None and proc.stdout is not None
        self._next_id += 1
        req = {"id": self._next_id, **req}
        proc.stdin.write(json.dumps(req, ensure_ascii=False).encode() + b"\n")
        await proc.stdin.drain()
        line = await asyncio.wait_for(proc.stdout.readline(), self.timeout)
        if not line:
            raise WorkerError("worker exited")
        reply = json.loads(line)
        if not isinstance(reply, dict) or reply.get("id") != req["id"]:
            raise WorkerError("worker reply out of order")
        return reply

    async def request(self, req: dict[str, Any]) -> dict[str, Any]:
        """Sends a request; on any failure restarts the worker and raises WorkerError."""
        async with self._lock:
            try:
                return await self._send(req)
            except (TimeoutError, OSError, ValueError, WorkerError) as e:
                with contextlib.suppress(Exception):
                    await self._restart()
                raise WorkerError(f"decision worker failed: {e or type(e).__name__}") from e

    async def load(self, policy: dict[str, Any]) -> int:
        """Loads rules. If Lean rejects them, raises RulesError and the old rules stay."""
        reply = await self.request({"op": "load", "policy": policy})
        if not reply.get("ok"):
            raise RulesError("the rule file was rejected", list(reply.get("errors", [])))
        self.policy = policy
        return int(reply["rules"])

    async def step(self, session: SessionState, call: dict[str, Any]) -> Decision:
        """Lean's decision on one call. Never raises: any failure is a deny."""
        try:
            reply = await self.request({"op": "step", "session": session.to_json(), "call": call})
            if not reply.get("ok"):
                return Decision.deny_on_error(str(reply.get("error", "worker error")), session)
            return Decision.from_json(reply)
        except (WorkerError, KeyError, TypeError, ValueError) as e:
            return Decision.deny_on_error(str(e), session)

    async def info(self) -> dict[str, Any]:
        reply = await self.request({"op": "info"})
        info = reply.get("info")
        if not isinstance(info, dict):
            raise WorkerError("worker info missing")
        return info
