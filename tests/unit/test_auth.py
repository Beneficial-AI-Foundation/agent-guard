from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import httpx2
import pytest
from cryptography.fernet import Fernet

from agentguard.auth.device_flow import device_login
from agentguard.auth.keyring_store import TokenStore
from agentguard.auth.tokens import StoredBearerAuth, StoredToken, refresh
from agentguard.errors import AuthError


def form(request: httpx2.Request) -> dict[str, str]:
    from urllib.parse import parse_qsl

    return dict(parse_qsl(request.content.decode()))


def test_device_flow() -> None:
    polls: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/login/device/code":
            assert form(request)["client_id"] == "Iv1.test"
            return httpx2.Response(
                200,
                json={
                    "device_code": "dc",
                    "user_code": "WDJB-MJHT",
                    "interval": 1,
                    "verification_uri": "https://github.com/login/device",
                    "expires_in": 900,
                },
            )
        body = form(request)
        assert body["grant_type"].endswith("device_code") and body["device_code"] == "dc"
        polls.append("x")
        if len(polls) == 1:
            return httpx2.Response(200, json={"error": "authorization_pending"})
        if len(polls) == 2:
            return httpx2.Response(200, json={"error": "slow_down", "interval": 2})
        return httpx2.Response(
            200,
            json={
                "access_token": "ghu_abc",
                "token_type": "bearer",
                "expires_in": 28800,
                "refresh_token": "ghr_def",
                "scope": "",
            },
        )

    shown: list[tuple[str, str]] = []
    waits: list[float] = []

    async def no_sleep(s: float) -> None:
        waits.append(s)

    async def go() -> StoredToken:
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as http:
            return await device_login(
                "Iv1.test",
                show=lambda u, c: shown.append((u, c)),
                http=http,
                base="https://gh.test",
                sleep=no_sleep,
            )

    token = asyncio.run(go())
    assert shown == [("https://github.com/login/device", "WDJB-MJHT")]
    assert waits == [1, 1, 2]
    assert token.access_token == "ghu_abc" and token.refresh_token == "ghr_def"
    assert token.token_url == "https://gh.test/login/oauth/access_token"
    assert token.expires_at is not None and token.expires_at > time.time() + 28000


def test_device_flow_denied() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/login/device/code":
            return httpx2.Response(
                200,
                json={"device_code": "d", "user_code": "U", "verification_uri": "v", "interval": 0},
            )
        return httpx2.Response(200, json={"error": "access_denied"})

    async def go() -> None:
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as http:

            async def no_sleep(s: float) -> None:
                pass

            await device_login(
                "c", show=lambda u, c: None, http=http, base="https://x", sleep=no_sleep
            )

    with pytest.raises(AuthError, match="cancelled"):
        asyncio.run(go())


def test_store_memory_and_encrypted_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mem = TokenStore("memory")
    mem.set("p/github", {"access_token": "x"})
    assert mem.get("p/github") == {"access_token": "x"}
    mem.delete("p/github")
    assert mem.get("p/github") is None

    path = tmp_path / "tokens.enc"
    with pytest.raises(AuthError, match="AGENTGUARD_TOKEN_KEY"):
        TokenStore("file", path).set("a", {"access_token": "secret-value"})
    monkeypatch.setenv("AGENTGUARD_TOKEN_KEY", Fernet.generate_key().decode())
    f = TokenStore("file", path)
    f.set("a", {"access_token": "secret-value"})
    assert b"secret-value" not in path.read_bytes()
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    assert TokenStore("file", path).get("a") == {"access_token": "secret-value"}


def test_bearer_auth_refreshes_expired_and_401() -> None:
    store = TokenStore("memory")
    old = StoredToken(
        "old",
        refresh_token="r1",
        expires_at=time.time() - 10,
        client_id="c",
        token_url="https://gh.test/token",
    )
    store.set("p/github", old.to_json())
    issued = iter(["new1", "new2"])

    async def refresher(t: StoredToken) -> StoredToken:
        return StoredToken(next(issued), refresh_token="r2", client_id="c", token_url=t.token_url)

    seen: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.headers["Authorization"])
        return httpx2.Response(401 if len(seen) == 2 else 200, json={})

    async def go() -> None:
        auth = StoredBearerAuth(store, "p/github", refresher)
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler), auth=auth) as c:
            assert (await c.get("https://api.test/a")).status_code == 200
            assert (await c.get("https://api.test/b")).status_code == 200

    asyncio.run(go())
    assert seen == ["Bearer new1", "Bearer new1", "Bearer new2"]
    assert store.get("p/github")["access_token"] == "new2"  # type: ignore[index]


def test_bearer_auth_not_signed_in() -> None:
    async def go() -> None:
        auth = StoredBearerAuth(TokenStore("memory"), "p/github")
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(lambda r: httpx2.Response(200)), auth=auth
        ) as c:
            await c.get("https://api.test/")

    with pytest.raises(AuthError, match="agentguard login"):
        asyncio.run(go())


def test_refresh_grant() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        body: dict[str, Any] = form(request)
        assert body == {"client_id": "c", "grant_type": "refresh_token", "refresh_token": "r"}
        return httpx2.Response(
            200, content=json.dumps({"access_token": "n", "refresh_token": "r2", "expires_in": 100})
        )

    async def go() -> StoredToken:
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as http:
            t = StoredToken(
                "o", refresh_token="r", client_id="c", token_url="https://x/t", login="octo"
            )
            return await refresh(t, http)

    new = asyncio.run(go())
    assert (new.access_token, new.refresh_token, new.login) == ("n", "r2", "octo")
