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

from ..errors import AgentGuardError
from ..profile.mcp_json import ServerConfig

#: Builds a Client for a server; tests use it to connect in-process servers.
ClientFactory = Callable[[ServerConfig], Client]


@dataclass(frozen=True)
class Route:
    """Which upstream tool an exposed tool name points to."""

    server: str
    tool: str
    spec: types.Tool


def default_client(cfg: ServerConfig) -> Client:
    if cfg.kind == "stdio":
        assert cfg.command is not None
        params = StdioServerParameters(
            command=cfg.command, args=cfg.args, env=cfg.env or None, cwd=cfg.cwd
        )
        return Client(params)
    assert cfg.url is not None
    http = httpx2.AsyncClient(headers=cfg.headers, timeout=httpx2.Timeout(30, read=300))
    return Client(streamable_http_client(cfg.url, http_client=http))


def _leaf(e: BaseException) -> BaseException:
    """The innermost error of an exception group (anyio wraps connection failures)."""
    while isinstance(e, BaseExceptionGroup) and e.exceptions:
        e = e.exceptions[0]
    return e


class UpstreamError(AgentGuardError):
    """A guarded server can't be reached or refused the connection."""

    def __init__(self, cfg: ServerConfig, e: BaseException) -> None:
        where = cfg.url or cfg.command
        hint = " Check the token in the profile's .env." if cfg.kind == "http" else ""
        super().__init__(f"{cfg.name}: can't connect to {where} ({_leaf(e)}).{hint}")


class Upstreams:
    def __init__(
        self,
        servers: list[ServerConfig],
        client_factory: ClientFactory | None = None,
    ) -> None:
        self.servers = servers
        self._factory = client_factory or default_client
        self._clients: dict[str, Client] = {}
        self.routes: dict[str, Route] = {}

    async def start(self, stack: AsyncExitStack) -> None:
        for cfg in self.servers:
            try:
                self._clients[cfg.name] = await stack.enter_async_context(self._factory(cfg))
            except AgentGuardError:
                raise
            except Exception as e:
                raise UpstreamError(cfg, e) from e
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
        return [
            r.spec.model_copy(update={"name": n, "output_schema": object_schema(r.spec)})
            for n, r in self.routes.items()
        ]

    async def call(self, server: str, tool: str, arguments: dict[str, Any]) -> types.CallToolResult:
        result = await self._clients[server].call_tool(tool, arguments)
        if result.structured_content is not None and not isinstance(
            result.structured_content, dict
        ):
            result = result.model_copy(update={"structured_content": None})
        return result


def object_schema(tool: types.Tool) -> dict[str, Any] | None:
    """The tool's output schema, if agents on any protocol version accept it.

    Before 2026-07-28, MCP requires `"type": "object"` at the root. GitHub's server sends
    schemas like `"type": ["object", "null"]` or a root `oneOf`, and passing those on makes
    the SDK reject the whole tool list. An output schema is optional (the same data is in
    the result's content), so such schemas are dropped, along with structured content that
    isn't an object.
    """
    schema = tool.output_schema
    return schema if schema is not None and schema.get("type") == "object" else None
