"""Live tests talk to real GitHub. They run only with AGENTGUARD_LIVE=1 and:

AGENTGUARD_LIVE_PROFILE  a profile folder that is signed in (agentguard init + login)
AGENTGUARD_LIVE_OWNER    the owner of demo-public and demo-private
AGENTGUARD_LIVE_TOKEN    a token used only by the checks (GitHub REST API), never by the agent
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

LIVE = os.environ.get("AGENTGUARD_LIVE") == "1"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/live" in str(item.fspath):
            item.add_marker(pytest.mark.live)
            if not LIVE:
                item.add_marker(pytest.mark.skip(reason="set AGENTGUARD_LIVE=1 to run live tests"))


@pytest.fixture(scope="session")
def live_profile() -> Path:
    return Path(os.environ["AGENTGUARD_LIVE_PROFILE"]).expanduser()


@pytest.fixture(scope="session")
def owner() -> str:
    return os.environ["AGENTGUARD_LIVE_OWNER"]
