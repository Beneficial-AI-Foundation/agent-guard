"""The one place a tool call is forwarded.

Lean decides; this code obeys. In `enforce` mode a call reaches the upstream
server only if Lean said allow, or said ask and a person approved. Every other
outcome, including any error from Lean, returns a readable "Blocked by
AgentGuard" message to the agent instead.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import mcp_types as types

from ..approvals import Answer, Approvals
from ..audit import fingerprint_all, redact
from ..monitor.worker import Decision, SessionState, Worker
from ..settings import Mode
from .session import AgentSession
from .upstream import Upstreams

EventSink = Callable[[dict[str, Any]], None]


class Guard:
    def __init__(
        self,
        worker: Worker,
        upstreams: Upstreams,
        approvals: Approvals,
        mode: Mode,
        labels: list[str],
        emit: EventSink,
    ) -> None:
        self.worker = worker
        self.upstreams = upstreams
        self.approvals = approvals
        self.mode = mode
        self.labels = labels
        self.emit = emit

    async def call(self, s: AgentSession, name: str, args: dict[str, Any]) -> types.CallToolResult:
        route = self.upstreams.routes.get(name)
        if route is None:
            return blocked(f"there is no tool named {name}.")
        call = {"server": route.server, "tool": route.tool, "arguments": args}
        async with s.lock:  # one decision at a time per session, so the state can't race
            s.calls += 1
            if self.mode is Mode.OFF:
                return await self._forward(s, call, None, "forwarded")
            d = await self.worker.step(s.state, call)
            if self.mode is Mode.AUDIT:
                return await self._forward(s, call, d, "forwarded")
            if d.verdict == "allow":
                return await self._forward(s, call, d, "allowed")
            if d.verdict == "ask":
                answer = await self._ask_person(s, call, d)
                if answer == "approved":
                    return await self._forward(s, call, d, "approved")
                return self._block(s, call, d, answer)
            return self._block(s, call, d, "denied")

    async def _ask_person(self, s: AgentSession, call: dict[str, Any], d: Decision) -> Answer:
        self._event(s, call, d, "waiting", s.state, s.state)
        return await self.approvals.request(
            session=s.key,
            server=call["server"],
            tool=call["tool"],
            arguments=call["arguments"],
            reason=self.why_ask(d, call["tool"]),
            rule=d.rule,
            context=list(s.outsider_text),
        )

    async def _forward(
        self, s: AgentSession, call: dict[str, Any], d: Decision | None, outcome: str
    ) -> types.CallToolResult:
        before = s.state
        try:
            result = await self.upstreams.call(call["server"], call["tool"], call["arguments"])
        except Exception as e:  # the call may or may not have run upstream
            result = types.CallToolResult(
                content=[types.TextContent(type="text", text=f"{call['tool']} failed: {e}")],
                is_error=True,
            )
            outcome = "upstream error"
        if d is not None:
            # A forwarded call counts as run, so the session absorbs what it read.
            s.state = d.next if d.verdict != "deny" else absorb(before, d)
            if d.untrusted:
                text = " ".join(content_text(result))
                if text.strip():
                    s.outsider_text.append(text[:500])
        self._event(s, call, d, outcome, before, s.state)
        return result

    def _block(
        self, s: AgentSession, call: dict[str, Any], d: Decision, answer: str
    ) -> types.CallToolResult:
        self._event(s, call, d, answer, s.state, s.state)
        tool = call["tool"]
        if answer == "rejected":
            return blocked(f"a person rejected {tool}. Ask them what to do instead.")
        if answer == "timeout":
            minutes = max(1, round(self.approvals.timeout / 60))
            return blocked(f"no one approved {tool} within {minutes} min.")
        return blocked(self.why_deny(d, tool, s.state))

    def why_deny(self, d: Decision, tool: str, state: SessionState) -> str:
        if d.cause == "rule":
            return (
                f"{tool} is not allowed for agents (rule {d.rule}: deny). "
                "Ask a person to do it, or take another route."
            )
        if d.cause == "no_rule":
            return f"{tool} isn't allowed by any rule, so it is denied by default."
        if d.cause == "leak":
            low = self.label(min(d.dests, default=0))
            return (
                f"this session has read {self.label(state.level)} data, and {tool} would "
                f"write to a {low} place. Writing there needs a new session."
            )
        return f"AgentGuard couldn't check {tool}, so it was blocked ({d.error})."

    def why_ask(self, d: Decision, tool: str) -> str:
        if d.cause == "untrusted":
            return f"The session read text from outsiders, so {tool} (high impact) needs a person."
        return f"Rule {d.rule} says a person must approve {tool}."

    def label(self, n: int) -> str:
        return self.labels[n] if 0 <= n < len(self.labels) else f"level {n}"

    def _event(
        self,
        s: AgentSession,
        call: dict[str, Any],
        d: Decision | None,
        outcome: str,
        before: SessionState,
        after: SessionState,
    ) -> None:
        self.emit(
            {
                "time": time.time(),
                "session": s.key,
                "server": call["server"],
                "tool": call["tool"],
                "arguments": (
                    fingerprint_all(call["arguments"])
                    if d is not None and d.cause == "leak"
                    else redact(call["arguments"])
                ),
                "mode": self.mode.value,
                "verdict": d.verdict if d else None,
                "cause": d.cause if d else None,
                "rule": d.rule if d else None,
                "theorem": d.theorem if d else None,
                "error": d.error if d else None,
                "outcome": outcome,
                "before": before.to_json(),
                "after": after.to_json(),
            }
        )


def absorb(s: SessionState, d: Decision) -> SessionState:
    """The session after a call Lean denied but audit mode forwarded anyway."""
    return SessionState(max(s.level, d.read_level), s.tainted or d.untrusted)


def content_text(result: types.CallToolResult) -> list[str]:
    """The text in a result: text blocks and embedded text resources (file contents)."""
    out: list[str] = []
    for c in result.content:
        if isinstance(c, types.TextContent):
            out.append(c.text)
        elif isinstance(c, types.EmbeddedResource) and isinstance(
            c.resource, types.TextResourceContents
        ):
            out.append(c.resource.text)
    return out


def blocked(reason: str) -> types.CallToolResult:
    text = f"Blocked by AgentGuard: {reason}"
    return types.CallToolResult(content=[types.TextContent(type="text", text=text)], is_error=True)
