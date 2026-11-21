"""The six GitHub demo stories, offline, through a real gateway and the Lean worker."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agentguard.demo import load_stories, run_all, template_dir

STORIES = [name for name, _ in load_stories(template_dir("github"))]


@pytest.mark.parametrize("name", STORIES)
def test_story(name: str, worker_binary: Path) -> None:
    [result] = asyncio.run(run_all("github", only=name))
    bad = [
        f"{s.call}: expected {s.expect}, got {s.got} ({s.message})"
        for s in result.steps
        if not s.ok
    ]
    bad += [f"check failed: {says}" for says, ok in result.checks if not ok]
    assert not bad, "\n".join(bad)


def test_six_stories() -> None:
    assert len(STORIES) == 6
