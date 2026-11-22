"""Live tests: the six stories against real GitHub, through the real gateway.

They run when AGENTGUARD_LIVE_OWNER is set (`make live OWNER=your-test-org`):

AGENTGUARD_LIVE_OWNER    the org that owns demo-public and demo-private
                         (created by scripts/setup_test_repos.sh)
AGENTGUARD_LIVE_PROFILE  the profile the gateway uses (default ~/.agentguard/github)
AGENTGUARD_LIVE_TOKEN    the token the checks use for the REST API (default: `gh auth token`);
                         the gateway never sees it
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

OWNER = os.environ.get("AGENTGUARD_LIVE_OWNER", "")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/live" in str(item.fspath):
            item.add_marker(pytest.mark.live)
            if not OWNER:
                item.add_marker(pytest.mark.skip(reason="set AGENTGUARD_LIVE_OWNER to run"))


@pytest.fixture(scope="session")
def live_profile() -> Path:
    return Path(os.environ.get("AGENTGUARD_LIVE_PROFILE", "~/.agentguard/github")).expanduser()


@pytest.fixture(scope="session")
def owner() -> str:
    return OWNER


@pytest.fixture(scope="session")
def check_token() -> str:
    token = os.environ.get("AGENTGUARD_LIVE_TOKEN")
    if not token:
        token = subprocess.run(
            ["gh", "auth", "token"],  # noqa: S607
            capture_output=True,
            text=True,
        ).stdout.strip()
    if not token:
        pytest.fail(
            "the checks need a GitHub token: run `gh auth login` or set AGENTGUARD_LIVE_TOKEN"
        )
    return token
