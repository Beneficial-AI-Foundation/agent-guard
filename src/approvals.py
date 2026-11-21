"""Calls waiting for a person ("ask" verdicts). No answer in time counts as reject."""

from __future__ import annotations

import asyncio
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Literal

Answer = Literal["approved", "rejected", "timeout"]


@dataclass
class Pending:
    id: str
    created: float
    session: str
    server: str
    tool: str
    arguments: dict[str, Any]
    #: Why a person is needed, in plain words.
    reason: str
    rule: int | None
    #: Recent outsider text the session read, shown so the person sees what steered the agent.
    context: list[str]
    future: asyncio.Future[bool] = field(repr=False)

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "created": self.created,
            "session": self.session,
            "server": self.server,
            "tool": self.tool,
            "arguments": self.arguments,
            "reason": self.reason,
            "rule": self.rule,
            "context": self.context,
        }


class Approvals:
    def __init__(self, timeout: float = 300.0) -> None:
        self.timeout = timeout
        self._pending: dict[str, Pending] = {}

    async def request(
        self,
        *,
        session: str,
        server: str,
        tool: str,
        arguments: dict[str, Any],
        reason: str,
        rule: int | None,
        context: list[str],
    ) -> Answer:
        loop = asyncio.get_running_loop()
        p = Pending(
            id=secrets.token_hex(4),
            created=time.time(),
            session=session,
            server=server,
            tool=tool,
            arguments=arguments,
            reason=reason,
            rule=rule,
            context=context,
            future=loop.create_future(),
        )
        self._pending[p.id] = p
        try:
            approved = await asyncio.wait_for(asyncio.shield(p.future), self.timeout)
            return "approved" if approved else "rejected"
        except TimeoutError:
            return "timeout"
        finally:
            self._pending.pop(p.id, None)

    def pending(self) -> list[Pending]:
        return sorted(self._pending.values(), key=lambda p: p.created)

    def answer(self, pending_id: str, approve: bool) -> bool:
        """Records a person's answer. False if there's no such pending call."""
        p = self._pending.get(pending_id)
        if p is None or p.future.done():
            return False
        p.future.set_result(approve)
        return True
