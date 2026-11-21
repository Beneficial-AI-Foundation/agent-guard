"""Lean and the Python reference must agree on every decision.

Random rule files and call sequences (10,000 cases by default; set
AGENTGUARD_PROPERTY_CASES to change) go through both. Any difference in verdict,
cause, rule, next session or classification fails the test.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
from pathlib import Path
from typing import Any

from agentguard.monitor import reference
from agentguard.monitor.worker import Worker

CASES = int(os.environ.get("AGENTGUARD_PROPERTY_CASES", "10000"))
SEED = int(os.environ.get("AGENTGUARD_PROPERTY_SEED", "20261120"))

LABELS = ["public", "internal", "private"]
REPO_PATS = [
    "*/demo-public",
    "*/demo-private",
    "octo/*",
    "**",
    "*",
    "Octo/Demo-*",
    "*/demo-?rivate",
    "*/DEMO-PUBLIC",
    "o?to/**",
]
TOOL_PATS = [
    "github.get_*",
    "github.push_files",
    "github.*",
    "**",
    "*",
    "github.?ush_files",
    "gh.push_files",
    "github.issue_read",
    "github.merge_pull_request",
    "*.*_*",
]
KEYS = ["branch", "path", "event", "owner", "n", "files"]
PATS = [
    "main",
    "fix/*",
    "**.github/**",
    "*",
    "**",
    "APPROVE",
    "?",
    "a**",
    "*.yml",
    "README.md",
    "é*",
    "true",
    "7",
    "[x]",
]
TOOLS = [
    "get_file_contents",
    "push_files",
    "issue_read",
    "merge_pull_request",
    "pull_request_review_write",
    "x",
    "push_file",
]
OWNERS = ["octo", "Octo", "OCTO", "o/x", ""]
REPOS = ["demo-public", "Demo-Private", "demo-private", "other", "DEMO-PUBLIC"]
STRINGS = [
    "main",
    "fix/a",
    "Main",
    "",
    ".github/workflows/x.yml",
    "README.md",
    "./.github/a",
    "a/b/c",
    "APPROVE",
    "approve",
    "é",
    "x y",
    "**",
]


def rand_policy(r: random.Random) -> dict[str, Any]:
    labels = LABELS[: r.randint(1, 3)]
    repos = [
        {"match": r.choice(REPO_PATS), "label": r.choice(labels)} for _ in range(r.randint(0, 4))
    ]
    rules = []
    for _ in range(r.randint(0, 8)):
        rule: dict[str, Any] = {
            "tool": r.choice(TOOL_PATS),
            "action": r.choice(["allow", "ask", "deny"]),
        }
        if r.random() < 0.6:
            when: dict[str, Any] = {}
            for k in r.sample(KEYS, r.randint(1, 2)):
                pats = r.sample(PATS, r.randint(1, 2))
                when[k] = pats[0] if len(pats) == 1 and r.random() < 0.5 else pats
            rule["when"] = when
        for field, opts in (
            ("effect", ["read", "write", "readwrite"]),
            ("source", ["trusted", "untrusted"]),
            ("impact", ["low", "high"]),
        ):
            if r.random() < 0.7:
                rule[field] = r.choice(opts)
        rules.append(rule)
    return {"labels": labels, "repos": repos, "rules": rules}


def rand_value(r: random.Random, depth: int = 0) -> Any:
    roll = r.random()
    if depth > 2 or roll < 0.5:
        return r.choice([*STRINGS, True, False, None, 7, -3, 0])
    if roll < 0.75:
        return [rand_value(r, depth + 1) for _ in range(r.randint(0, 3))]
    return {r.choice(KEYS): rand_value(r, depth + 1) for _ in range(r.randint(0, 3))}


def rand_call(r: random.Random) -> dict[str, Any]:
    args: dict[str, Any] = {}
    if r.random() < 0.85:
        args["owner"] = r.choice(OWNERS)
    if r.random() < 0.85:
        args["repo"] = r.choice(REPOS) if r.random() < 0.95 else 5
    for k in r.sample(KEYS, r.randint(0, 3)):
        args[k] = rand_value(r)
    if r.random() < 0.4:
        args["files"] = [
            {"path": r.choice(STRINGS), "content": "…"} for _ in range(r.randint(0, 3))
        ]
    return {
        "server": r.choice(["github", "github", "gh"]),
        "tool": r.choice(TOOLS),
        "arguments": args,
    }


async def compare(binary: Path) -> int:
    r = random.Random(SEED)
    steps = 0
    async with Worker(binary, timeout=10) as w:
        for case in range(CASES):
            pol = rand_policy(r)
            reply = await w.request({"op": "load", "policy": pol})
            assert reply["ok"], (case, reply)
            ref = reference.Policy.from_json(pol)
            session = {"level": r.randrange(len(pol["labels"])), "tainted": r.random() < 0.3}
            for _ in range(r.randint(1, 6)):
                call = rand_call(r)
                lean = await w.request({"op": "step", "session": session, "call": call})
                assert lean.pop("ok"), (case, lean)
                lean.pop("id")
                lean.pop("theorem")
                want = reference.step(ref, session, call)
                assert lean == want, (
                    f"case {case} disagrees\npolicy={json.dumps(pol)}\n"
                    f"session={session}\ncall={json.dumps(call)}\nlean={lean}\nref={want}"
                )
                steps += 1
                approved = r.random() < 0.5
                if lean["verdict"] == "allow" or (lean["verdict"] == "ask" and approved):
                    session = lean["next"]
    return steps


def test_lean_and_reference_agree(worker_binary: Path) -> None:
    steps = asyncio.run(compare(worker_binary))
    assert steps >= CASES
