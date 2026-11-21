"""The gateway: an MCP server for the agent, in front of the upstream servers."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import secrets
import time
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import Any

import mcp_types as types
from mcp.server.lowlevel import Server
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from .. import __version__
from ..approvals import Approvals
from ..audit import AuditLog, EventFeed, fingerprint
from ..errors import AgentGuardError, RulesError
from ..monitor.worker import Worker
from ..profile import rules
from ..profile.loader import Profile
from ..settings import Settings
from .guard import Guard
from .session import SessionStore
from .upstream import AuthFactory, ClientFactory, Upstreams


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


class Gateway:
    def __init__(
        self,
        profile: Profile,
        settings: Settings,
        worker: Worker,
        upstreams: Upstreams,
        audit: AuditLog,
    ) -> None:
        self.profile = profile
        self.settings = settings
        self.worker = worker
        self.upstreams = upstreams
        self.audit = audit
        self.feed = EventFeed()
        self.approvals = Approvals(settings.approval_timeout)
        self.sessions = SessionStore()
        self.policy_hash = profile.policy_hash
        self.worker_hash = file_hash(worker.binary)
        self.theorems: list[str] = []
        self.started = time.time()
        self.guard = Guard(
            worker,
            upstreams,
            self.approvals,
            settings.mode,
            list(profile.policy.get("labels", [])),
            self.emit,
        )
        self.default_session = "stdio"

    @classmethod
    @asynccontextmanager
    async def open(
        cls,
        profile: Profile,
        settings: Settings,
        *,
        audit_path: Path | None = None,
        client_factory: ClientFactory | None = None,
        auth: AuthFactory | None = None,
    ) -> AsyncIterator[Gateway]:
        async with AsyncExitStack() as stack:
            worker = await stack.enter_async_context(Worker(timeout=settings.worker_timeout))
            await worker.load(profile.policy)
            upstreams = Upstreams(profile.servers, client_factory, auth)
            await upstreams.start(stack)
            gw = cls(profile, settings, worker, upstreams, AuditLog(audit_path))
            gw.theorems = list((await worker.info()).get("theorems", []))
            gw.emit({"kind": "start", "outcome": "started", "mode": settings.mode.value})
            yield gw

    def emit(self, event: dict[str, Any]) -> None:
        event = {"policy": self.policy_hash, "worker": self.worker_hash, **event}
        event = self.feed.add(event)
        self.audit.write(event)

    # The MCP server the agent talks to

    def session_key(self, ctx: Any) -> str:
        """Which AgentGuard session a call belongs to.

        MCP 2026-07-28 over HTTP is stateless (no session id) and the SDK builds a
        new session object per request, so neither can identify an agent: keying on
        them would let an agent reset its session level just by reconnecting.
        AgentGuard therefore defines the session by the agent's identity: one per
        `agentguard stdio` process, and one per gateway token over HTTP. Merging
        calls into one session only ever raises the level, so it is the safe choice.
        A person can end a session from the console.
        """
        request = getattr(ctx, "request", None)
        headers = getattr(request, "headers", None)
        if headers is not None:
            auth = headers.get("authorization")
            return "agent-" + fingerprint(auth)[7:15] if auth else "http"
        return self.default_session

    def end_session(self, key: str) -> bool:
        """Forgets a session's state (a person's decision, from the console)."""
        ended = self.sessions.end(key)
        if ended:
            self.emit({"kind": "session", "session": key, "outcome": "ended"})
        return ended

    def mcp_server(self) -> Server[Any]:
        async def list_tools(
            ctx: Any, params: types.PaginatedRequestParams | None
        ) -> types.ListToolsResult:
            return types.ListToolsResult(tools=self.upstreams.tools())

        async def call_tool(ctx: Any, params: types.CallToolRequestParams) -> types.CallToolResult:
            s = self.sessions.get(self.session_key(ctx))
            return await self.guard.call(s, params.name, dict(params.arguments or {}))

        return Server(
            "agentguard",
            version=__version__,
            instructions=(
                "Tool calls pass through AgentGuard, which checks each one against the "
                "project's rules. A blocked call returns a message saying why."
            ),
            on_list_tools=list_tools,
            on_call_tool=call_tool,
        )

    # Rules reload when the file is saved; a rejected file leaves the old rules in force.

    async def reload_rules(self) -> list[str]:
        try:
            policy = rules.load(self.profile.rules_path)
            await self.worker.load(policy)
        except RulesError as e:
            self.emit({"kind": "rules", "outcome": "rejected", "problems": e.problems or [str(e)]})
            return e.problems or [str(e)]
        except AgentGuardError as e:
            self.emit({"kind": "rules", "outcome": "rejected", "problems": [str(e)]})
            return [str(e)]
        self.policy_hash = rules.policy_hash(policy)
        self.guard.labels = list(policy.get("labels", []))
        self.emit({"kind": "rules", "outcome": "reloaded"})
        return []

    async def watch_rules(self, interval: float = 1.0) -> None:
        path = self.profile.rules_path
        last = path.stat().st_mtime_ns if path.exists() else 0
        while True:
            await asyncio.sleep(interval)
            with contextlib.suppress(OSError):
                now = path.stat().st_mtime_ns
                if now != last:
                    last = now
                    await self.reload_rules()

    def status(self) -> dict[str, Any]:
        return {
            "version": __version__,
            "profile": str(self.profile.folder),
            "mode": self.guard.mode.value,
            "servers": [s.name for s in self.profile.servers],
            "tools": len(self.upstreams.routes),
            "policy": self.policy_hash,
            "rules": (self.worker.policy or {}).get("rules", []),
            "labels": self.guard.labels,
            "worker": self.worker_hash,
            "theorems": self.theorems,
            "started": self.started,
            "sessions": [s.to_json() for s in self.sessions.all()],
        }


async def serve_stdio(gw: Gateway) -> None:
    from mcp.server.stdio import stdio_server

    server = gw.mcp_server()
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


class BearerCheck:
    """Requires `Authorization: Bearer <token>` on the MCP endpoint."""

    def __init__(self, app: ASGIApp, token: str | None) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self.token and scope["type"] == "http" and scope["path"].startswith("/mcp"):
            headers = dict(scope.get("headers") or [])
            got = headers.get(b"authorization", b"").decode()
            if not secrets.compare_digest(got, f"Bearer {self.token}"):
                await JSONResponse({"error": "missing or wrong AgentGuard token"}, 401)(
                    scope, receive, send
                )
                return
        await self.app(scope, receive, send)


def http_app(gw: Gateway, token: str | None) -> ASGIApp:
    async def healthz(request: Request) -> Response:
        return JSONResponse({"ok": True})

    server = gw.mcp_server()
    app = server.streamable_http_app(
        streamable_http_path="/mcp",
        host=gw.settings.gateway_host,
        custom_starlette_routes=[Route("/healthz", healthz)],
    )
    return BearerCheck(app, token)
