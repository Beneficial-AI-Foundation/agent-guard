"""The whole gateway against the neutral echo server (no GitHub)."""

from __future__ import annotations

import asyncio
import json
import socket
import sys
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx2
import mcp_types as types
import pytest
import uvicorn
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from agentguard.profile import loader
from agentguard.profile.mcp_json import ServerConfig
from agentguard.proxy.server import Gateway, http_app
from agentguard.settings import Mode, Settings

from ..fixtures import echo_server

ECHO = Path(echo_server.__file__)

RULES = """
labels: [public, private]
servers:
  - name: echo
    resource: {keys: [owner, repo]}
resources:
  - {match: "*/public", label: public}
  - {match: "*/private", label: private}
rules:
  - {tool: echo.read_doc, action: allow, effect: read, source: trusted, impact: low}
  - {tool: echo.read_comment, action: allow, effect: read, source: untrusted, impact: low}
  - {tool: echo.write_doc, when: {branch: main}, action: deny, effect: write}
  - {tool: echo.write_doc, when: {path: "secret/**"}, action: ask, effect: write}
  - {tool: echo.write_doc, action: allow, effect: write, source: trusted, impact: high}
  - {tool: echo.publish, action: allow, effect: write, source: trusted, impact: low}
  - {tool: echo.merge, action: deny}
"""

PUB = {"owner": "o", "repo": "public"}
PRIV = {"owner": "o", "repo": "private"}


def make_profile(folder: Path, rules: str = RULES) -> loader.Profile:
    mcp = {"servers": {"echo": {"command": sys.executable, "args": [str(ECHO)]}}}
    (folder / "mcp.json").write_text(json.dumps(mcp))
    (folder / "rules.yaml").write_text(rules)
    return loader.load(folder)


def in_process(cfg: ServerConfig) -> Client:
    return Client(echo_server.make_server())


@asynccontextmanager
async def gateway(
    tmp_path: Path, mode: Mode = Mode.ENFORCE, timeout: float = 5.0, real_stdio: bool = False
) -> AsyncIterator[tuple[Gateway, Client]]:
    profile = make_profile(tmp_path)
    settings = Settings(mode=mode, approval_timeout=timeout)
    echo_server.received.clear()
    async with (
        Gateway.open(
            profile,
            settings,
            audit_path=tmp_path / "audit.jsonl",
            client_factory=None if real_stdio else in_process,
        ) as gw,
        Client(gw.mcp_server()) as agent,
    ):
        yield gw, agent


def text(r: types.CallToolResult) -> str:
    return " ".join(c.text for c in r.content if isinstance(c, types.TextContent))


def received() -> list[str]:
    return [c["tool"] for c in echo_server.received]


def run(f: Callable[[], Any]) -> None:
    asyncio.run(f())


@pytest.fixture(autouse=True)
def _need_worker(worker_binary: Path) -> None:
    pass


def test_lists_upstream_tools(tmp_path: Path) -> None:
    async def go() -> None:
        async with gateway(tmp_path) as (_, agent):
            names = [t.name for t in (await agent.list_tools()).tools]
            assert names == echo_server.TOOLS

    run(go)


def test_allow_deny_and_default(tmp_path: Path) -> None:
    async def go() -> None:
        async with gateway(tmp_path) as (gw, agent):
            r = await agent.call_tool("write_doc", {**PUB, "branch": "fix", "path": "a"})
            assert not r.is_error and received() == ["write_doc"]
            r = await agent.call_tool("merge", PUB)
            assert r.is_error and "Blocked by AgentGuard: merge is not allowed" in text(r)
            assert "rule 7" in text(r)
            r = await agent.call_tool("write_doc", {**PUB, "path": "a"})  # no branch = main
            assert r.is_error and "rule 3" in text(r)
            r = await agent.call_tool("delete_doc", PUB)
            assert r.is_error and "isn't allowed by any rule" in text(r)
            r = await agent.call_tool("nope", {})
            assert r.is_error and "no tool named nope" in text(r)
            assert received() == ["write_doc"]  # nothing denied reached the server
            outcomes = [e.get("outcome") for e in gw.feed.since(0)]
            assert outcomes == ["started", "allowed", "denied", "denied", "denied"]

    run(go)


def test_leak_is_denied(tmp_path: Path) -> None:
    async def go() -> None:
        async with gateway(tmp_path) as (_, agent):
            assert not (await agent.call_tool("publish", {**PUB, "body": "fine"})).is_error
            assert not (
                await agent.call_tool("read_doc", {"owner": "O", "repo": "PRIVATE"})
            ).is_error
            r = await agent.call_tool("publish", {**PUB, "body": "KEY=…"})
            assert r.is_error and "read private data" in text(r)
            assert not (await agent.call_tool("publish", {**PRIV, "body": "ok"})).is_error
            assert received() == ["publish", "read_doc", "publish"]

    run(go)


def test_reconnecting_does_not_reset_the_session(tmp_path: Path) -> None:
    async def go() -> None:
        async with gateway(tmp_path) as (gw, agent):
            await agent.call_tool("read_doc", PRIV)
            async with Client(gw.mcp_server()) as again:  # a fresh connection, same agent
                r = await again.call_tool("publish", PUB)
                assert r.is_error and "read private data" in text(r)
            assert gw.end_session("stdio")  # a person ends the session in the console
            assert not (await agent.call_tool("publish", PUB)).is_error

    run(go)


async def answer_when_asked(gw: Gateway, approve: bool) -> None:
    while not gw.approvals.pending():
        await asyncio.sleep(0.01)
    p = gw.approvals.pending()[0]
    assert gw.approvals.answer(p.id, approve)


def test_ask_approved_and_rejected(tmp_path: Path) -> None:
    async def go() -> None:
        async with gateway(tmp_path) as (gw, agent):
            args = {**PUB, "branch": "fix", "path": "secret/x"}
            helper = asyncio.create_task(answer_when_asked(gw, True))
            r = await agent.call_tool("write_doc", args)
            await helper
            assert not r.is_error and received() == ["write_doc"]
            helper = asyncio.create_task(answer_when_asked(gw, False))
            r = await agent.call_tool("write_doc", args)
            await helper
            assert r.is_error and "a person rejected" in text(r)
            assert received() == ["write_doc"]

    run(go)


def test_ask_times_out(tmp_path: Path) -> None:
    async def go() -> None:
        async with gateway(tmp_path, timeout=0.2) as (_, agent):
            r = await agent.call_tool("write_doc", {**PUB, "branch": "fix", "path": "secret/x"})
            assert r.is_error and "no one approved" in text(r)
            assert received() == []

    run(go)


def test_untrusted_text_needs_a_person(tmp_path: Path) -> None:
    async def go() -> None:
        async with gateway(tmp_path) as (gw, agent):
            await agent.call_tool("read_comment", PUB)
            helper = asyncio.create_task(answer_when_asked(gw, False))
            r = await agent.call_tool("write_doc", {**PUB, "branch": "fix", "path": "a"})
            await helper
            assert r.is_error
            # the approval card showed the outsider text that came before
            ev = next(e for e in gw.feed.since(0) if e.get("outcome") == "waiting")
            assert ev["cause"] == "untrusted"
            assert not (await agent.call_tool("publish", {**PUB, "body": "low impact"})).is_error

    run(go)


def test_approval_card_shows_outsider_text(tmp_path: Path) -> None:
    async def go() -> None:
        async with gateway(tmp_path) as (gw, agent):
            await agent.call_tool("read_comment", PUB)
            args = {**PUB, "branch": "f", "path": "a"}
            task = asyncio.create_task(agent.call_tool("write_doc", args))
            while not gw.approvals.pending():
                await asyncio.sleep(0.01)
            p = gw.approvals.pending()[0]
            assert "IGNORE PREVIOUS INSTRUCTIONS" in p.context[0]
            assert "outsiders" in p.reason
            gw.approvals.answer(p.id, False)
            await task

    run(go)


def test_audit_mode_forwards_and_records(tmp_path: Path) -> None:
    async def go() -> None:
        async with gateway(tmp_path, mode=Mode.AUDIT) as (gw, agent):
            await agent.call_tool("read_doc", PRIV)
            assert not (await agent.call_tool("merge", PUB)).is_error
            assert not (await agent.call_tool("publish", PUB)).is_error  # would leak
            ev = gw.feed.since(0)[-2:]
            assert [(e["verdict"], e["outcome"]) for e in ev] == [
                ("deny", "forwarded"),
                ("deny", "forwarded"),
            ]
            assert received() == ["read_doc", "merge", "publish"]

    run(go)


def test_off_mode_forwards_without_checking(tmp_path: Path) -> None:
    async def go() -> None:
        async with gateway(tmp_path, mode=Mode.OFF) as (gw, agent):
            assert not (await agent.call_tool("merge", PUB)).is_error
            assert gw.feed.since(0)[-1]["verdict"] is None

    run(go)


def test_rules_reload_and_rejected_file(tmp_path: Path) -> None:
    async def go() -> None:
        async with gateway(tmp_path) as (gw, agent):
            rules_path = tmp_path / "rules.yaml"
            rules_path.write_text(
                RULES.replace(
                    "{tool: echo.merge, action: deny}",
                    "{tool: echo.merge, action: allow, effect: write, "
                    "source: trusted, impact: low}",
                )
            )
            assert await gw.reload_rules() == []
            assert not (await agent.call_tool("merge", PUB)).is_error
            rules_path.write_text("labels: [public]\nrules: [{tool: x, acton: deny}]\n")
            problems = await gw.reload_rules()
            assert any("acton" in p for p in problems)
            assert not (await agent.call_tool("merge", PUB)).is_error  # previous rules stay

    run(go)


def test_audit_log_redacts(tmp_path: Path) -> None:
    async def go() -> None:
        async with gateway(tmp_path) as (_, agent):
            token = "ghp_" + "a" * 36
            await agent.call_tool("publish", {**PUB, "body": f"leaked {token}", "api_key": "k1"})

    run(go)
    log = (tmp_path / "audit.jsonl").read_text()
    assert "ghp_aaaa" not in log and "k1" not in log
    lines = [json.loads(x) for x in log.splitlines()]
    assert all(x["v"] == 1 for x in lines)
    assert lines[-1]["arguments"]["api_key"].startswith("<redacted sha256:")


def test_denied_leak_is_not_copied_into_the_log(tmp_path: Path) -> None:
    async def go() -> None:
        async with gateway(tmp_path) as (_, agent):
            await agent.call_tool("read_doc", PRIV)
            r = await agent.call_tool("publish", {**PUB, "body": "here it is: s3cr3t-v4lue"})
            assert r.is_error

    run(go)
    assert "s3cr3t-v4lue" not in (tmp_path / "audit.jsonl").read_text()


def test_real_stdio_upstream(tmp_path: Path) -> None:
    async def go() -> None:
        async with gateway(tmp_path, real_stdio=True) as (_, agent):
            r = await agent.call_tool("write_doc", {**PUB, "branch": "fix", "path": "a"})
            assert not r.is_error and json.loads(text(r))["tool"] == "write_doc"
            assert (await agent.call_tool("merge", PUB)).is_error

    run(go)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_http_gateway_with_token(tmp_path: Path) -> None:
    async def go() -> None:
        async with gateway(tmp_path) as (gw, _):
            port = free_port()
            config = uvicorn.Config(
                http_app(gw, "s3cret"), host="127.0.0.1", port=port, log_level="warning"
            )
            server = uvicorn.Server(config)
            task = asyncio.create_task(server.serve())
            while not server.started:
                await asyncio.sleep(0.02)
            url = f"http://127.0.0.1:{port}/mcp"
            try:
                http = httpx2.AsyncClient(headers={"Authorization": "Bearer s3cret"})
                async with Client(streamable_http_client(url, http_client=http)) as agent:
                    assert (await agent.call_tool("merge", PUB)).is_error
                    r = await agent.call_tool("publish", {**PUB, "body": "hi"})
                    assert not r.is_error
                async with httpx2.AsyncClient() as raw:
                    resp = await raw.post(url, json={})
                    assert resp.status_code == 401
            finally:
                server.should_exit = True
                await task

    run(go)
