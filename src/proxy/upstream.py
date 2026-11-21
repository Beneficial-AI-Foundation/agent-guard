"""Connections from AgentGuard to the real MCP servers (GitHub), over stdio or HTTP."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any

import httpx2
import mcp_types as types
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.client.streamable_http import streamable_http_client

from ..errors import AuthError
from ..profile.mcp_json import ServerConfig

#: Builds an httpx2 auth for a server that signs in with OAuth (see `auth/`).
AuthFactory = Callable[[ServerConfig], httpx2.Auth | None]
#: Builds a Client for a server; tests use it to connect in-process servers.
ClientFactory = Callable[[ServerConfig], Client]


@dataclass(frozen=True)
class Route:
    """Which upstream tool an exposed tool name points to."""

    server: str
    tool: str
    spec: types.Tool


def default_client(cfg: ServerConfig, auth: AuthFactory | None = None) -> Client:
    if cfg.kind == "stdio":
        assert cfg.command is not None
        params = StdioServerParameters(
            command=cfg.command, args=cfg.args, env=cfg.env or None, cwd=cfg.cwd
        )
        return Client(params)
    assert cfg.url is not None
    http_auth = auth(cfg) if (auth is not None and cfg.auth == "oauth") else None
    if cfg.auth == "oauth" and http_auth is None:
        raise AuthError(f"{cfg.name}: not signed in; run `agentguard login`")
    http = httpx2.AsyncClient(
        headers=cfg.headers, auth=http_auth, timeout=httpx2.Timeout(30, read=300)
    )
    return Client(streamable_http_client(cfg.url, http_client=http))


class Upstreams:
    def __init__(
        self,
        servers: list[ServerConfig],
        client_factory: ClientFactory | None = None,
        auth: AuthFactory | None = None,
    ) -> None:
        self.servers = servers
        self._factory = client_factory or (lambda cfg: default_client(cfg, auth))
        self._clients: dict[str, Client] = {}
        self.routes: dict[str, Route] = {}

    async def start(self, stack: AsyncExitStack) -> None:
        for cfg in self.servers:
            self._clients[cfg.name] = await stack.enter_async_context(self._factory(cfg))
        await self.refresh_tools()

    async def refresh_tools(self) -> None:
        """Exposes each server's tools. With one server the names stay as they are, so
        agents see the same tools as without AgentGuard; with several, `server__tool`."""
        routes: dict[str, Route] = {}
        prefix = len(self._clients) > 1
        for name, client in self._clients.items():
            cursor: str | None = None
            while True:
                page = await client.list_tools(cursor=cursor)
                for t in page.tools:
                    exposed = f"{name}__{t.name}" if prefix else t.name
                    routes[exposed] = Route(name, t.name, t)
                cursor = page.next_cursor
                if not cursor:
                    break
        self.routes = routes

    def tools(self) -> list[types.Tool]:
        return [r.spec.model_copy(update={"name": n}) for n, r in self.routes.items()]

    async def call(self, server: str, tool: str, arguments: dict[str, Any]) -> types.CallToolResult:
        return await self._clients[server].call_tool(tool, arguments)
