"""MCP-standard OAuth (discovery, PKCE, dynamic client registration) for remote
servers that support it, using the MCP SDK. GitHub uses the device flow instead
(see `device_flow.py`)."""

from __future__ import annotations

import asyncio
import contextlib
import socket
import webbrowser
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qs, urlparse

from mcp.client.auth import AuthorizationCodeResult, OAuthClientProvider
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken
from pydantic import AnyUrl

from ..errors import AuthError
from .keyring_store import TokenStore


class StoreAdapter:
    """The SDK's `TokenStorage`, kept in AgentGuard's token store."""

    def __init__(self, store: TokenStore, account: str) -> None:
        self.store = store
        self.account = account

    def _data(self) -> dict[str, Any]:
        return self.store.get(self.account) or {}

    async def get_tokens(self) -> OAuthToken | None:
        t = self._data().get("mcp_tokens")
        return OAuthToken.model_validate(t) if t else None

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self.store.set(self.account, {**self._data(), "mcp_tokens": tokens.model_dump()})

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        c = self._data().get("mcp_client")
        return OAuthClientInformationFull.model_validate(c) if c else None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        data = {**self._data(), "mcp_client": client_info.model_dump(mode="json")}
        self.store.set(self.account, data)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class LocalCallback:
    """Receives the OAuth redirect on http://127.0.0.1:<port>/callback."""

    def __init__(self) -> None:
        self.port = _free_port()
        self.result: asyncio.Future[AuthorizationCodeResult] | None = None

    @property
    def redirect_uri(self) -> str:
        return f"http://127.0.0.1:{self.port}/callback"

    async def wait(self, timeout: float = 300) -> AuthorizationCodeResult:
        loop = asyncio.get_running_loop()
        self.result = loop.create_future()

        async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            line = (await reader.readline()).decode()
            path = line.split(" ")[1] if " " in line else "/"
            q = parse_qs(urlparse(path).query)
            ok = "code" in q
            body = "Signed in. You can close this tab." if ok else "Sign-in failed."
            writer.write(f"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\n{body}".encode())
            await writer.drain()
            writer.close()
            if ok and self.result and not self.result.done():
                self.result.set_result(
                    AuthorizationCodeResult(
                        code=q["code"][0],
                        state=q.get("state", [None])[0],
                        iss=q.get("iss", [None])[0],
                    )
                )

        server = await asyncio.start_server(handle, "127.0.0.1", self.port)
        try:
            return await asyncio.wait_for(self.result, timeout)
        except TimeoutError as e:
            raise AuthError("no sign-in within 5 minutes") from e
        finally:
            server.close()
            with contextlib.suppress(Exception):
                await server.wait_closed()


def provider(
    server_url: str,
    store: TokenStore,
    account: str,
    *,
    interactive: bool,
    say: Callable[[str], None] = print,
) -> OAuthClientProvider:
    """An httpx2 auth for an MCP server. Non-interactive (while serving) it never
    opens a browser: a missing sign-in is an error telling the person to log in."""
    callback = LocalCallback()

    async def redirect(url: str) -> None:
        if not interactive:
            raise AuthError(f"{account}: not signed in; run `agentguard login`")
        say(f"Opening your browser to sign in. If it doesn't open, visit:\n  {url}")
        webbrowser.open(url)

    async def wait_for_code() -> AuthorizationCodeResult:
        return await callback.wait()

    metadata = OAuthClientMetadata(
        client_name="AgentGuard",
        redirect_uris=[AnyUrl(callback.redirect_uri)],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        token_endpoint_auth_method="none",  # noqa: S106 - public client, not a password
    )
    return OAuthClientProvider(
        server_url=server_url,
        client_metadata=metadata,
        storage=StoreAdapter(store, account),
        redirect_handler=redirect,
        callback_handler=wait_for_code,
    )
