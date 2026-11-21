"""`agentguard stdio` as a real process, between a real MCP client and the echo server."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import mcp_types as types
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from .test_gateway import PUB, make_profile


def test_stdio_process_end_to_end(tmp_path: Path, worker_binary: Path) -> None:
    make_profile(tmp_path)
    log = tmp_path / "echo.log"
    # Like VS Code, the MCP SDK gives a server only a safe subset of the environment;
    # anything else goes in the server's "env" in mcp.json.
    mcp = json.loads((tmp_path / "mcp.json").read_text())
    mcp["servers"]["echo"]["env"] = {"ECHO_LOG": str(log)}
    (tmp_path / "mcp.json").write_text(json.dumps(mcp))
    env = {**os.environ, "AGENTGUARD_WORKER": str(worker_binary)}
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "agentguard", "stdio", "--profile", str(tmp_path), "--no-console"],
        env=env,
    )

    async def go() -> None:
        async with Client(params) as agent:
            assert "merge" in [t.name for t in (await agent.list_tools()).tools]
            r = await agent.call_tool("merge", PUB)
            assert r.is_error
            assert isinstance(r.content[0], types.TextContent)
            assert r.content[0].text.startswith("Blocked by AgentGuard")
            assert not (await agent.call_tool("publish", {**PUB, "body": "hi"})).is_error

    asyncio.run(go())
    reached = [json.loads(x)["tool"] for x in log.read_text().splitlines()]
    assert reached == ["publish"]  # the denied merge never reached the server
    audit = [json.loads(x) for x in (tmp_path / "audit.jsonl").read_text().splitlines()]
    assert [e.get("outcome") for e in audit] == ["started", "denied", "allowed"]


def test_check_command(tmp_path: Path, worker_binary: Path) -> None:
    make_profile(tmp_path)
    env = {**os.environ, "AGENTGUARD_WORKER": str(worker_binary)}
    ok = subprocess.run(
        [sys.executable, "-m", "agentguard", "check", "--profile", str(tmp_path)],
        capture_output=True,
        text=True,
        env=env,
    )
    assert ok.returncode == 0 and "7 rules" in ok.stdout
    (tmp_path / "rules.yaml").write_text("labels: [a]\nrules: [{tool: x}]\n")
    bad = subprocess.run(
        [sys.executable, "-m", "agentguard", "check", "--profile", str(tmp_path)],
        capture_output=True,
        text=True,
        env=env,
    )
    assert bad.returncode == 1 and "action is missing" in bad.stderr
