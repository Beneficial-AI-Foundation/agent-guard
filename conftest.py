from __future__ import annotations

import os
from pathlib import Path

import pytest

from agentguard.errors import WorkerError
from agentguard.monitor.worker import find_binary

REPO = Path(__file__).resolve().parent


@pytest.fixture(scope="session")
def worker_binary() -> Path:
    """The Lean worker. Skipped if it isn't built, unless AGENTGUARD_REQUIRE_WORKER=1 (CI)."""
    try:
        return find_binary()
    except WorkerError:
        if os.environ.get("AGENTGUARD_REQUIRE_WORKER") == "1":
            raise
        pytest.skip("guard-worker not built (run `make proofs`)")
