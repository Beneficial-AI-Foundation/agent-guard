"""GitHub sign-in with the device flow: the person opens github.com/login/device and
types a short code. Needs only a client ID (no secret), so it works from a CLI.

Use a GitHub App (recommended: its tokens are limited to the repositories it is
installed on, and expire) or an OAuth App, with "device flow" enabled.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

import httpx2

from ..errors import AuthError
from .tokens import StoredToken

GITHUB = "https://github.com"
GRANT = "urn:ietf:params:oauth:grant-type:device_code"


async def device_login(
    client_id: str,
    *,
    scope: str = "",
    show: Callable[[str, str], None],
    http: httpx2.AsyncClient,
    base: str = GITHUB,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> StoredToken:
    """Runs the device flow. `show(url, code)` tells the person what to do."""
    headers = {"Accept": "application/json"}
    resp = await http.post(
        f"{base}/login/device/code", data={"client_id": client_id, "scope": scope}, headers=headers
    )
    start = resp.json()
    if "device_code" not in start:
        raise AuthError(f"GitHub refused the sign-in: {start.get('error_description') or start}")
    show(start["verification_uri"], start["user_code"])
    interval = float(start.get("interval", 5))
    deadline = time.monotonic() + float(start.get("expires_in", 900))
    token_url = f"{base}/login/oauth/access_token"
    while time.monotonic() < deadline:
        await sleep(interval)
        resp = await http.post(
            token_url,
            data={"client_id": client_id, "device_code": start["device_code"], "grant_type": GRANT},
            headers=headers,
        )
        body = resp.json()
        error = body.get("error")
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            interval = float(body.get("interval", interval + 5))
            continue
        if error == "access_denied":
            raise AuthError("sign-in was cancelled on GitHub")
        if error == "expired_token":
            break
        return StoredToken.from_response(body, client_id, token_url)
    raise AuthError("the sign-in code expired; run `agentguard login` again")


async def github_login_name(token: StoredToken, http: httpx2.AsyncClient, api: str) -> str | None:
    resp = await http.get(
        f"{api}/user",
        headers={"Authorization": f"Bearer {token.access_token}", "Accept": "application/json"},
    )
    if resp.status_code != 200:
        return None
    login = resp.json().get("login")
    return str(login) if login else None
