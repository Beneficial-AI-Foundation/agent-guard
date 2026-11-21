"""Signing in to upstream servers: GitHub's device flow, or MCP-standard OAuth."""

from __future__ import annotations

import os
from urllib.parse import urlparse

import httpx2

from ..profile.mcp_json import ServerConfig
from ..proxy.upstream import AuthFactory
from .keyring_store import TokenStore
from .tokens import StoredBearerAuth, StoredToken, refresh

GITHUB_HOSTS = ("api.githubcopilot.com", "github.com", "api.github.com")


def is_github(cfg: ServerConfig) -> bool:
    host = urlparse(cfg.url or "").hostname or ""
    return host in GITHUB_HOSTS or host.endswith(".ghe.com")


def account(profile: str, server: str) -> str:
    return f"{profile}/{server}"


def github_client_id() -> str | None:
    """The GitHub App or OAuth App AgentGuard signs in with (device flow enabled)."""
    return os.environ.get("AGENTGUARD_GITHUB_CLIENT_ID") or None


def auth_factory(profile: str, store: TokenStore) -> AuthFactory:
    """Builds the auth for each `oauth` server when the gateway starts."""

    async def refresher(token: StoredToken) -> StoredToken:
        async with httpx2.AsyncClient(timeout=30) as http:
            return await refresh(token, http)

    def make(cfg: ServerConfig) -> httpx2.Auth | None:
        acct = account(profile, cfg.name)
        if is_github(cfg):
            return StoredBearerAuth(store, acct, refresher)
        from .oauth import provider

        assert cfg.url is not None
        return provider(cfg.url, store, acct, interactive=False)

    return make
