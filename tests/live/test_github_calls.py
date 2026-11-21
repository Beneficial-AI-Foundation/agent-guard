"""Scripted calls through the gateway to the real GitHub MCP server, then checks
with the GitHub REST API (using a separate token the agent never sees)."""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx2
import mcp_types as types
from mcp import Client

from agentguard.auth import auth_factory
from agentguard.auth.keyring_store import TokenStore
from agentguard.profile import loader
from agentguard.proxy.server import Gateway
from agentguard.settings import Settings

API = "https://api.github.com"


def rest(path: str) -> Any:
    headers = {
        "Authorization": f"Bearer {os.environ['AGENTGUARD_LIVE_TOKEN']}",
        "Accept": "application/vnd.github+json",
    }
    r = httpx2.get(f"{API}{path}", headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()


def main_sha(owner: str, repo: str) -> str:
    return str(rest(f"/repos/{owner}/{repo}/branches/main")["commit"]["sha"])


@asynccontextmanager
async def agent(profile_dir: Path) -> AsyncIterator[tuple[Gateway, Client]]:
    profile = loader.load(profile_dir)
    auth = auth_factory(profile.name, TokenStore())
    settings = Settings(approval_timeout=1)
    async with Gateway.open(profile, settings, auth=auth) as gw, Client(gw.mcp_server()) as c:
        yield gw, c


def text(r: types.CallToolResult) -> str:
    return " ".join(c.text for c in r.content if isinstance(c, types.TextContent))


def test_template_tool_names_exist(live_profile: Path) -> None:
    """Every tool the rules name exists on the live server (catches renamed tools)."""

    async def go() -> None:
        async with agent(live_profile) as (gw, _):
            live = {f"{r.server}.{r.tool}" for r in gw.upstreams.routes.values()}
            named = {r["tool"] for r in gw.profile.policy["rules"] if "*" not in r["tool"]}
            missing = sorted(named - live)
            assert not missing, f"rules name tools the server doesn't have: {missing}"

    asyncio.run(go())


def test_denials_change_nothing(live_profile: Path, owner: str) -> None:
    before = main_sha(owner, "demo-public")
    pub = {"owner": owner, "repo": "demo-public"}

    async def go() -> None:
        async with agent(live_profile) as (_, c):
            r = await c.call_tool(
                "push_files",
                {
                    **pub,
                    "branch": "main",
                    "message": "x",
                    "files": [{"path": "README.md", "content": "x"}],
                },
            )
            assert r.is_error and "Blocked by AgentGuard" in text(r)
            pulls = rest(f"/repos/{owner}/demo-public/pulls?state=open")
            if pulls:
                r = await c.call_tool(
                    "merge_pull_request", {**pub, "pullNumber": pulls[0]["number"]}
                )
                assert r.is_error and "Blocked by AgentGuard" in text(r)

    asyncio.run(go())
    assert main_sha(owner, "demo-public") == before


def test_leak_is_denied(live_profile: Path, owner: str) -> None:
    issues = rest(f"/repos/{owner}/demo-public/issues?state=open")
    target = issues[0]["number"]

    async def go() -> None:
        async with agent(live_profile) as (_, c):
            r = await c.call_tool(
                "get_file_contents", {"owner": owner, "repo": "demo-private", "path": "config.env"}
            )
            assert not r.is_error and "fake-deploy-key" in text(r)
            r = await c.call_tool(
                "add_issue_comment",
                {
                    "owner": owner,
                    "repo": "demo-public",
                    "issue_number": target,
                    "body": "config: fake-deploy-key-3f9a",
                },
            )
            assert r.is_error and "read private data" in text(r)

    asyncio.run(go())
    comments = rest(f"/repos/{owner}/demo-public/issues/{target}/comments")
    assert not any("fake-deploy-key" in c["body"] for c in comments)


def test_normal_day_branch_and_push(live_profile: Path, owner: str) -> None:
    branch = f"agentguard-live-{int(time.time())}"
    pub = {"owner": owner, "repo": "demo-public"}
    before = main_sha(owner, "demo-public")

    async def go() -> None:
        async with agent(live_profile) as (_, c):
            r = await c.call_tool("create_branch", {**pub, "branch": branch})
            assert not r.is_error, text(r)
            r = await c.call_tool(
                "push_files",
                {
                    **pub,
                    "branch": branch,
                    "message": "Live test",
                    "files": [{"path": "LIVE.md", "content": "ok\n"}],
                },
            )
            assert not r.is_error, text(r)

    asyncio.run(go())
    assert rest(f"/repos/{owner}/demo-public/branches/{branch}")["name"] == branch
    assert main_sha(owner, "demo-public") == before
