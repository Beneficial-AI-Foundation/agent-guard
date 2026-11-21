"""The local console: live feed, approval cards, sessions, rules and proofs.

It binds to localhost only. Every API call needs the per-run console token (sent
as the `X-AgentGuard-Token` header; the page gets it from the URL fragment, which
browsers never send to servers), and the Host header must be a loopback address,
which blocks other web pages and DNS-rebinding attacks from answering approvals.
"""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import TYPE_CHECKING, Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Receive, Scope, Send

if TYPE_CHECKING:
    from ..proxy.server import Gateway

STATIC = Path(__file__).parent / "static"
_LOOPBACK = ("127.0.0.1", "localhost", "[::1]")


class Guarded:
    """Loopback Host header everywhere; the console token on /api/."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers") or []}
            host = headers.get("host", "").rsplit(":", 1)[0]
            if host not in _LOOPBACK:
                await JSONResponse({"error": "console is local only"}, 403)(scope, receive, send)
                return
            if scope["path"].startswith("/api/") and not secrets.compare_digest(
                headers.get("x-agentguard-token", ""), self.token
            ):
                await JSONResponse({"error": "console token required"}, 401)(scope, receive, send)
                return
        await self.app(scope, receive, send)


def make_app(gw: Gateway, token: str) -> ASGIApp:
    async def index(request: Request) -> Response:
        return FileResponse(STATIC / "index.html")

    async def healthz(request: Request) -> Response:
        return JSONResponse({"ok": True})

    async def readyz(request: Request) -> Response:
        proc = gw.worker._proc
        ready = proc is not None and proc.returncode is None and bool(gw.upstreams.routes)
        return JSONResponse({"ready": ready}, 200 if ready else 503)

    async def status(request: Request) -> Response:
        return JSONResponse(gw.status())

    async def events(request: Request) -> Response:
        since = int(request.query_params.get("since", "0"))
        return JSONResponse({"events": gw.feed.since(since), "last": gw.feed.last})

    async def approvals(request: Request) -> Response:
        return JSONResponse([p.to_json() for p in gw.approvals.pending()])

    async def answer(request: Request) -> Response:
        body: dict[str, Any] = await request.json()
        ok = gw.approvals.answer(request.path_params["id"], bool(body.get("approve")))
        return JSONResponse({"ok": ok}, 200 if ok else 404)

    async def end_session(request: Request) -> Response:
        ok = gw.end_session(request.path_params["key"])
        return JSONResponse({"ok": ok}, 200 if ok else 409)

    app = Starlette(
        routes=[
            Route("/", index),
            Route("/healthz", healthz),
            Route("/readyz", readyz),
            Route("/api/status", status),
            Route("/api/events", events),
            Route("/api/approvals", approvals),
            Route("/api/approvals/{id}", answer, methods=["POST"]),
            Route("/api/sessions/{key}/end", end_session, methods=["POST"]),
            Mount("/static", StaticFiles(directory=STATIC)),
        ]
    )
    return Guarded(app, token)
