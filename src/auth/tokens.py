"""Stored tokens, expiry and refresh, and an httpx2 auth that adds them to requests."""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import asdict, dataclass
from typing import Any

import httpx2

from ..errors import AuthError
from .keyring_store import TokenStore


@dataclass
class StoredToken:
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - a token type, not a secret
    scope: str | None = None
    refresh_token: str | None = None
    #: Unix time the access token expires, if it does.
    expires_at: float | None = None
    #: Who issued it, so it can be refreshed.
    client_id: str | None = None
    token_url: str | None = None
    login: str | None = None

    def expired(self, margin: float = 60) -> bool:
        return self.expires_at is not None and time.time() > self.expires_at - margin

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> StoredToken:
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__})  # type: ignore[arg-type]

    @classmethod
    def from_response(
        cls, body: dict[str, Any], client_id: str | None, token_url: str | None
    ) -> StoredToken:
        if "access_token" not in body:
            raise AuthError(f"sign-in failed: {body.get('error_description') or body}")
        expires_in = body.get("expires_in")
        return cls(
            access_token=str(body["access_token"]),
            token_type=str(body.get("token_type", "bearer")),
            scope=body.get("scope"),
            refresh_token=body.get("refresh_token"),
            expires_at=time.time() + float(expires_in) if expires_in else None,
            client_id=client_id,
            token_url=token_url,
        )


async def refresh(token: StoredToken, http: httpx2.AsyncClient) -> StoredToken:
    """OAuth refresh-token grant (GitHub App user tokens expire after 8 hours)."""
    if not (token.refresh_token and token.token_url and token.client_id):
        raise AuthError("the sign-in expired; run `agentguard login` again")
    resp = await http.post(
        token.token_url,
        data={
            "client_id": token.client_id,
            "grant_type": "refresh_token",
            "refresh_token": token.refresh_token,
        },
        headers={"Accept": "application/json"},
    )
    new = StoredToken.from_response(resp.json(), token.client_id, token.token_url)
    new.login = token.login
    return new


Refresher = Callable[[StoredToken], Awaitable[StoredToken]]


class StoredBearerAuth(httpx2.Auth):
    """Adds the stored token; refreshes it when it has expired or the server says 401."""

    def __init__(self, store: TokenStore, account: str, refresher: Refresher | None = None) -> None:
        self.store = store
        self.account = account
        self.refresher = refresher

    def _load(self) -> StoredToken:
        data = self.store.get(self.account)
        if data is None:
            raise AuthError(f"{self.account}: not signed in; run `agentguard login`")
        return StoredToken.from_json(data)

    async def _refresh(self, token: StoredToken) -> StoredToken:
        if self.refresher is None:
            raise AuthError(f"{self.account}: the sign-in expired; run `agentguard login`")
        new = await self.refresher(token)
        self.store.set(self.account, new.to_json())
        return new

    async def async_auth_flow(
        self, request: httpx2.Request
    ) -> AsyncGenerator[httpx2.Request, httpx2.Response]:
        token = self._load()
        if token.expired():
            token = await self._refresh(token)
        request.headers["Authorization"] = f"Bearer {token.access_token}"
        response = yield request
        if response.status_code == 401 and token.refresh_token:
            token = await self._refresh(token)
            request.headers["Authorization"] = f"Bearer {token.access_token}"
            yield request
