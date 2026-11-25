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

#: Lean's constructors, as a rule file spells them.
CAPABILITY = {
    "networkScan": "network_scan",
    "remoteAccess": "remote_access",
    "packetForge": "packet_forge",
    "malwareExec": "malware_exec",
    "serviceDisrupt": "service_disrupt",
    "auditTamper": "audit_tamper",
    "guardConfigWrite": "guard_config_write",
    "sendMessage": "send_message",
    "automatedDecision": "automated_decision",
    "operatePhysicalSystem": "operate_physical_system",
    "readData": "read_data",
    "writeData": "write_data",
}

# denyCap .x / askCap .x / decideRule "pat" / guardConfigByPath
LEAN_RULE = re.compile(r'(denyCap|askCap) \.(\w+)|decideRule "([^"]+)"|(guardConfigByPath)')

Entry = tuple[str, str, dict[str, str]]


def lean_template() -> list[Entry]:
    text = LEAN.read_text()
    deny = text.split("def frontierDeny")[1].split("def frontierAsk")[0]
    ask = text.split("def frontierAsk")[1].split("def frontierTemplate")[0]
    out: list[Entry] = []
    for block in (deny, ask):
        for kind, cap, domain, by_path in LEAN_RULE.findall(block):
            if by_path:
                out.append(("write_data", "deny", {"path": "**agentguard/**"}))
            elif domain:
                out.append(("automated_decision", "ask", {"domain": domain}))
            else:
                out.append((CAPABILITY[cap], "deny" if kind == "denyCap" else "ask", {}))
    return out


def yaml_template() -> list[Entry]:
    policy = rules.load(YAML)
    return [(r["capability"], r["action"], dict(r.get("when", {}))) for r in policy["rules"]]


def test_yaml_matches_lean() -> None:
    lean = lean_template()
    assert len(lean) == 20
    assert yaml_template() == lean


def test_every_capability_is_a_real_one() -> None:
    """The vocabulary is closed: the worker rejects anything outside it."""
    caps = {c for c, _, _ in yaml_template()}
    assert caps <= set(CAPABILITY.values())


#: A connection declaring one tool per capability the template uses.
TOOLS = {
    "network_scan": "scan",
    "packet_forge": "forge",
    "remote_access": "login",
    "malware_exec": "run",
    "audit_tamper": "edit_log",
    "guard_config_write": "write_config",
    "write_data": "write",
    "service_disrupt": "flood",
    "operate_physical_system": "actuate",
    "send_message": "send",
    "automated_decision": "decide",
}


def demo_policy() -> dict[str, Any]:
    policy = rules.load(YAML)
    policy["servers"] = [{"name": "demo", "capabilities": {c: [t] for c, t in TOOLS.items()}}]
    policy["rules"].append(
        {"tool": "**", "action": "allow", "effect": "read", "source": "trusted", "impact": "low"}
    )
    return policy


def example_call(cap: str, when: dict[str, str]) -> dict[str, Any]:
    """A call the rule for `cap` catches: every `*` in a condition becomes `x`."""
    return {
        "server": "demo",
        "tool": TOOLS[cap],
        "arguments": {k: v.replace("*", "x") for k, v in when.items()},
    }


def test_template_decides_before_later_rules(worker_binary: Path) -> None:
    policy = demo_policy()

    async def go() -> None:
        async with Worker(worker_binary) as w:
            assert await w.load(policy) == 21
            for cap, action, when in yaml_template():
                d = await w.step(SessionState(), example_call(cap, when))
                assert d.verdict == action, (cap, when, d)
            # Not caught by the template: the catch-all decides.
            for call in (
                {"server": "demo", "tool": "decide", "arguments": {"domain": "scheduling"}},
                {"server": "demo", "tool": "write", "arguments": {"path": "README.md"}},
                {"server": "demo", "tool": "read_note", "arguments": {}},
            ):
                assert (await w.step(SessionState(), call)).verdict == "allow", call

    asyncio.run(go())


def test_undeclared_server_is_untouched(worker_binary: Path) -> None:
    """The template reaches only what a connection declared.

    A server that declares nothing keeps the behaviour it would have had if the
    template were absent — the point of `capability_needs_declaration`.
    """
    policy = demo_policy()

    async def go() -> None:
        async with Worker(worker_binary) as w:
            await w.load(policy)
            for tool in ("send", "scan", "actuate"):
                call: dict[str, Any] = {"server": "other", "tool": tool, "arguments": {}}
                assert (await w.step(SessionState(), call)).verdict == "allow", call

    asyncio.run(go())
