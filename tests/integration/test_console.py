from __future__ import annotations

import asyncio
from pathlib import Path

import httpx2

from agentguard.console.app import make_app
from agentguard.proxy.server import Gateway
from agentguard.settings import Settings

from .test_gateway import PUB, in_process, make_profile

TOKEN = "console-token"


def test_console_api(tmp_path: Path, worker_binary: Path) -> None:
    async def go() -> None:
        profile = make_profile(tmp_path)
        async with Gateway.open(profile, Settings(), client_factory=in_process) as gw:
            app = make_app(gw, TOKEN)
            transport = httpx2.ASGITransport(app=app)
            base = "http://127.0.0.1:7070"
            h = {"X-AgentGuard-Token": TOKEN}
            async with httpx2.AsyncClient(transport=transport, base_url=base) as c:
                assert (await c.get("/healthz")).json() == {"ok": True}
                assert (await c.get("/readyz")).status_code == 200
                assert (await c.get("/")).status_code == 200
                assert (await c.get("/api/status")).status_code == 401
                assert (
                    await c.get("/api/status", headers={"X-AgentGuard-Token": "x"})
                ).status_code == 401
                status = (await c.get("/api/status", headers=h)).json()
                assert status["servers"] == ["echo"] and len(status["theorems"]) == 10

                # an approval answered through the console
                s = gw.sessions.get("stdio")
                call = asyncio.create_task(
                    gw.guard.call(s, "write_doc", {**PUB, "branch": "b", "path": "secret/x"})
                )
                while not (pending := (await c.get("/api/approvals", headers=h)).json()):
                    await asyncio.sleep(0.01)
                assert pending[0]["tool"] == "write_doc"
                r = await c.post(
                    f"/api/approvals/{pending[0]['id']}", headers=h, json={"approve": True}
                )
                assert r.json() == {"ok": True}
                assert not (await call).is_error
                events = (await c.get("/api/events?since=0", headers=h)).json()["events"]
                assert [e["outcome"] for e in events][-2:] == ["waiting", "approved"]
                assert (await c.post("/api/sessions/stdio/end", headers=h)).json() == {"ok": True}

            # another website (or DNS rebinding) can't reach it
            async with httpx2.AsyncClient(transport=transport, base_url="http://evil.test") as c:
                assert (await c.get("/api/status", headers=h)).status_code == 403
                assert (await c.get("/")).status_code == 403

    asyncio.run(go())
