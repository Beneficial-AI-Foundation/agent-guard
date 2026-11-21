"""Runs a template's demo stories through a real gateway, against the template's
offline mock server. Used by `agentguard demo` and by `examples/*/tests`.

A story is a YAML file: a list of tool calls with the verdict each should get
(and, for `ask`, whether the person approves), then checks on the mock server's
state (functions in the template's `demo/mock_server.py`).
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

import mcp_types as types
import yaml
from mcp import Client

from .profile import rules
from .profile.loader import Profile
from .profile.mcp_json import ServerConfig
from .proxy.server import Gateway
from .settings import Settings

TEMPLATES = Path(__file__).resolve().parent / "templates"


@dataclass
class StepResult:
    call: str
    expect: str
    got: str | None
    rule: int | None
    theorem: str | None
    message: str
    person: str | None = None

    @property
    def ok(self) -> bool:
        return self.expect == self.got


@dataclass
class StoryResult:
    name: str
    title: str
    summary: str
    theorem: str | None
    steps: list[StepResult] = field(default_factory=list)
    checks: list[tuple[str, bool]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(s.ok for s in self.steps) and all(ok for _, ok in self.checks)


def template_dir(name: str) -> Path:
    d = TEMPLATES / name
    if not d.is_dir():
        raise FileNotFoundError(f"no template named {name!r}")
    return d


def load_mock(template: Path) -> ModuleType:
    path = template / "demo" / "mock_server.py"
    name = f"agentguard_mock_{template.name}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_stories(template: Path) -> list[tuple[str, dict[str, Any]]]:
    files = sorted((template / "demo" / "stories").glob("*.yaml"))
    return [(f.stem, yaml.safe_load(f.read_text(encoding="utf-8"))) for f in files]


def demo_profile(template: Path, mock: ModuleType) -> Profile:
    policy = rules.load(template / "rules.yaml")
    server = ServerConfig(
        name=template.name, kind="stdio", command=sys.executable, args=[str(mock.__file__)]
    )
    return Profile(template, [server], policy, rules.policy_hash(policy))


async def _answer(gw: Gateway, approve: bool) -> None:
    while not gw.approvals.pending():
        await asyncio.sleep(0.005)
    gw.approvals.answer(gw.approvals.pending()[0].id, approve)


async def run_story(
    template: Path, mock: ModuleType, name: str, story: dict[str, Any]
) -> StoryResult:
    mock.reset()
    result = StoryResult(name, story["title"], story["summary"], story.get("theorem"))
    profile = demo_profile(template, mock)
    settings = Settings(approval_timeout=10)
    async with (
        Gateway.open(
            profile, settings, client_factory=lambda cfg: Client(mock.make_server())
        ) as gw,
        Client(gw.mcp_server()) as agent,
    ):
        for step in story["steps"]:
            person = step.get("person")
            helper = None
            if step["expect"] == "ask":
                helper = asyncio.create_task(_answer(gw, person == "approve"))
            r = await agent.call_tool(step["call"], step.get("args", {}))
            if helper is not None:
                helper.cancel()
            event: dict[str, Any] = next(
                (
                    e
                    for e in reversed(gw.feed.since(0))
                    if e.get("tool") == step["call"] and e.get("outcome") != "waiting"
                ),
                {},
            )
            text = " ".join(c.text for c in r.content if isinstance(c, types.TextContent))
            result.steps.append(
                StepResult(
                    call=step["call"],
                    expect=step["expect"],
                    got=event.get("verdict"),
                    rule=event.get("rule"),
                    theorem=event.get("theorem"),
                    message=text,
                    person=person if step["expect"] == "ask" else None,
                )
            )
    for check in story.get("checks", []):
        ok = getattr(mock, check["check"])(*check.get("args", [])) == check.get("expect", True)
        result.checks.append((check.get("says", check["check"]), ok))
    return result


async def run_all(template_name: str = "github", only: str | None = None) -> list[StoryResult]:
    template = template_dir(template_name)
    mock = load_mock(template)
    out = []
    for name, story in load_stories(template):
        if only and not name.startswith(only):
            continue
        out.append(await run_story(template, mock, name, story))
    return out
