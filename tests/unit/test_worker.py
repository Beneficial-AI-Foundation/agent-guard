from __future__ import annotations

import asyncio
import stat
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

import pytest

from agentguard.errors import RulesError
from agentguard.monitor.worker import SessionState, Worker

POLICY = {
    "labels": ["public", "private"],
    "repos": [{"match": "*/demo-private", "label": "private"}],
    "rules": [
        {"tool": "github.get_*", "action": "allow", "effect": "read", "source": "trusted"},
        {"tool": "github.merge_pull_request", "action": "deny"},
    ],
}
MERGE = {"server": "github", "tool": "merge_pull_request", "arguments": {}}


def run(coro: Coroutine[Any, Any, None]) -> None:
    asyncio.run(coro)


def test_decisions(worker_binary: Path) -> None:
    async def go() -> None:
        async with Worker(worker_binary) as w:
            assert await w.load(POLICY) == 2
            d = await w.step(SessionState(), MERGE)
            assert (d.verdict, d.cause, d.rule) == ("deny", "rule", 2)
            assert d.theorem == "deny_rule_always_denies"
            read = {
                "server": "github",
                "tool": "get_file_contents",
                "arguments": {"owner": "o", "repo": "demo-private"},
            }
            d = await w.step(SessionState(), read)
            assert d.verdict == "allow" and d.next == SessionState(level=1)
            info = await w.info()
            assert "no_exfiltration" in info["theorems"]

    run(go())


def test_rejected_rules_keep_old_ones(worker_binary: Path) -> None:
    async def go() -> None:
        async with Worker(worker_binary) as w:
            await w.load(POLICY)
            with pytest.raises(RulesError) as e:
                await w.load({"labels": ["public"], "rules": [{"tool": "x", "whne": {}}]})
            assert any("whne" in p for p in e.value.problems)
            assert w.policy == POLICY
            assert (await w.step(SessionState(), MERGE)).rule == 2

    run(go())


def test_no_policy_means_deny(worker_binary: Path) -> None:
    async def go() -> None:
        async with Worker(worker_binary) as w:
            d = await w.step(SessionState(), MERGE)
            assert d.verdict == "deny" and d.cause == "error"
            assert d.error is not None and "no policy" in d.error

    run(go())


def test_crash_is_deny_then_recovers(worker_binary: Path) -> None:
    async def go() -> None:
        async with Worker(worker_binary) as w:
            await w.load(POLICY)
            assert w._proc is not None
            w._proc.kill()
            await w._proc.wait()
            d = await w.step(SessionState(), MERGE)
            assert d.verdict == "deny" and d.cause == "error"
            d = await w.step(SessionState(), MERGE)  # restarted with the same rules
            assert d.cause == "rule" and d.rule == 2

    run(go())


def fake_worker(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "fake-worker"
    p.write_text(f"#!/usr/bin/env python3\nimport sys, time\n{body}\n")
    p.chmod(p.stat().st_mode | stat.S_IXUSR)
    return p


def test_hanging_worker_is_deny(tmp_path: Path) -> None:
    binary = fake_worker(tmp_path, "time.sleep(60)")

    async def go() -> None:
        w = Worker(binary, timeout=0.3)
        d = await w.step(SessionState(), MERGE)
        assert d.verdict == "deny" and d.error is not None
        await w.close()

    run(go())


def test_garbage_reply_is_deny(tmp_path: Path) -> None:
    binary = fake_worker(
        tmp_path,
        'for line in sys.stdin:\n    print(\'{"id": 1, "ok": true, "verdict": "yes"}\', '
        "flush=True)",
    )

    async def go() -> None:
        w = Worker(binary, timeout=2)
        d = await w.step(SessionState(), MERGE)
        assert d.verdict == "deny" and d.cause == "error"
        await w.close()

    run(go())
