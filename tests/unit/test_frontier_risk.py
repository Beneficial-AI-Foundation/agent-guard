"""The frontier-risk template (docs/frontier-risk-rules.yaml).

Checks that the rule file matches `frontierTemplate` in
lean/Guard/Rulesets/FrontierRisk.lean (where its guarantees are proved), that
the Lean worker accepts it, and that each of its rules still decides its calls
when a catch-all allow follows the template.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from agentguard.monitor.worker import SessionState, Worker
from agentguard.profile import rules

ROOT = Path(__file__).resolve().parents[2]
YAML = ROOT / "docs" / "frontier-risk-rules.yaml"
LEAN = ROOT / "lean" / "Guard" / "Rulesets" / "FrontierRisk.lean"

# denyRule "tool", denyRule "tool" [⟨"key", ["pat"]⟩], askRule "tool", decideRule "pat"
LEAN_RULE = re.compile(
    r'(denyRule|askRule|decideRule) "([^"]+)"(?: \[⟨"([^"]+)", \["([^"]+)"\]⟩\])?'
)


def lean_template() -> list[tuple[str, str, dict[str, str]]]:
    text = LEAN.read_text()
    deny = text.split("def frontierDeny")[1].split("def frontierAsk")[0]
    ask = text.split("def frontierAsk")[1].split("def frontierTemplate")[0]
    out: list[tuple[str, str, dict[str, str]]] = []
    for block in (deny, ask):
        for kind, arg, key, pat in LEAN_RULE.findall(block):
            if kind == "decideRule":
                out.append(("*.decide_*", "ask", {"domain": arg}))
            else:
                out.append(
                    (arg, "deny" if kind == "denyRule" else "ask", {key: pat} if key else {})
                )
    return out


def yaml_template() -> list[tuple[str, str, dict[str, str]]]:
    policy = rules.load(YAML)
    return [(r["tool"], r["action"], dict(r.get("when", {}))) for r in policy["rules"]]


def test_yaml_matches_lean() -> None:
    lean = lean_template()
    assert len(lean) == 31
    assert yaml_template() == lean


def example_call(tool: str, when: dict[str, str]) -> dict[str, Any]:
    """A call that the rule `tool` / `when` catches: every `*` becomes `x`."""
    server, name = tool.replace("*", "x").split(".", 1)
    args = {k: v.replace("*", "x") for k, v in when.items()}
    return {"server": server, "tool": name, "arguments": args}


def test_template_decides_before_later_rules(worker_binary: Path) -> None:
    policy = rules.load(YAML)
    policy["rules"].append(
        {"tool": "**", "action": "allow", "effect": "read", "source": "trusted", "impact": "low"}
    )

    async def go() -> None:
        async with Worker(worker_binary) as w:
            assert await w.load(policy) == 32
            for tool, action, when in yaml_template():
                d = await w.step(SessionState(), example_call(tool, when))
                assert d.verdict == action, (tool, when, d)
            # Not caught by the template: the catch-all decides.
            for call in (
                {"server": "hr", "tool": "decide_x", "arguments": {"domain": "scheduling"}},
                {"server": "github", "tool": "push_files", "arguments": {"path": "README.md"}},
                {"server": "notes", "tool": "read_note", "arguments": {}},
            ):
                assert (await w.step(SessionState(), call)).verdict == "allow", call

    asyncio.run(go())
