"""An independent Python copy of the Lean spec, **for tests only**.

`tests/property/test_lean_vs_reference.py` runs thousands of random rule files
and call sequences through both this and the Lean worker and requires identical
answers. Glob matching here uses a different algorithm (memoised backtracking
over positions) from Lean's (pattern derivatives), so the two cross-check.

It expects rule files that Lean has accepted; it does not validate them.
Keep it in step with `lean/Guard/Spec/` (CONTRIBUTING rule 2).
"""

from __future__ import annotations

import json
import string
from dataclasses import dataclass
from functools import cache
from typing import Any

_LOWER = str.maketrans(string.ascii_uppercase, string.ascii_lowercase)


def lower(s: str) -> str:
    """ASCII-only, like Lean's `Char.toLower`."""
    return s.translate(_LOWER)


def tokenize(pat: str) -> tuple[str, ...]:
    """Tokens: '**', '*', '?' or a single literal character (prefixed with 'L')."""
    out: list[str] = []
    i = 0
    while i < len(pat):
        if pat.startswith("**", i):
            out.append("**")
            i += 2
        elif pat[i] in "*?":
            out.append(pat[i])
            i += 1
        else:
            out.append("L" + pat[i])
            i += 1
    return tuple(out)


def glob(pat: str, s: str) -> bool:
    toks = tokenize(pat)

    @cache
    def m(i: int, j: int) -> bool:
        if i == len(toks):
            return j == len(s)
        t = toks[i]
        if t == "**":
            return m(i + 1, j) or (j < len(s) and m(i, j + 1))
        if t == "*":
            return m(i + 1, j) or (j < len(s) and s[j] != "/" and m(i, j + 1))
        if j == len(s):
            return False
        if t == "?":
            return s[j] != "/" and m(i + 1, j + 1)
        return t[1] == s[j] and m(i + 1, j + 1)

    return m(0, 0)


def _scalar(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    return json.dumps(v)


def leaves(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [v]
    if isinstance(v, list):
        return [x for item in v for x in leaves(item)]
    if isinstance(v, dict):
        return [x for item in v.values() for x in leaves(item)]
    return [_scalar(v)]


def values_at(key: str, v: Any) -> list[str]:
    if isinstance(v, list):
        return [x for item in v for x in values_at(key, item)]
    if isinstance(v, dict):
        out: list[str] = []
        for k, item in v.items():
            if k == key:
                out += leaves(item)
            out += values_at(key, item)
        return out
    return []


@dataclass(frozen=True)
class Rule:
    tool: str
    conds: tuple[tuple[str, tuple[str, ...]], ...]
    action: str
    reads: bool
    writes: bool
    untrusted: bool
    high_impact: bool


@dataclass(frozen=True)
class Policy:
    label_count: int
    repos: tuple[tuple[str, int], ...]
    rules: tuple[Rule, ...]

    @property
    def top(self) -> int:
        return self.label_count - 1

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> Policy:
        labels = list(d["labels"])
        rules = []
        for r in d["rules"]:
            effect = r.get("effect", "readwrite")
            when = r.get("when") or {}
            conds = tuple((k, (v,) if isinstance(v, str) else tuple(v)) for k, v in when.items())
            rules.append(
                Rule(
                    tool=r["tool"],
                    conds=conds,
                    action=r["action"],
                    reads=effect in ("read", "readwrite"),
                    writes=effect in ("write", "readwrite"),
                    untrusted=r.get("source", "untrusted") == "untrusted",
                    high_impact=r.get("impact", "high") == "high",
                )
            )
        repos = tuple((e["match"], labels.index(e["label"])) for e in d.get("repos") or [])
        return cls(len(labels), repos, tuple(rules))


def cond_holds(action: str, key: str, pats: tuple[str, ...], args: dict[str, Any]) -> bool:
    vals = values_at(key, args)

    def accepts(v: str) -> bool:
        return any(glob(p, v) for p in pats)

    if action == "allow":
        return bool(vals) and all(accepts(v) for v in vals)
    return not vals or any(accepts(v) for v in vals)


def applies(r: Rule, call: dict[str, Any]) -> bool:
    name = f"{call['server']}.{call['tool']}"
    args = call.get("arguments") or {}
    return glob(r.tool, name) and all(cond_holds(r.action, k, p, args) for k, p in r.conds)


def first_match(p: Policy, call: dict[str, Any]) -> tuple[int, Rule] | None:
    for i, r in enumerate(p.rules):
        if applies(r, call):
            return i, r
    return None


def _as_str(v: Any) -> str | None:
    """A top-level scalar as Lean's wire layer sees it (numbers and booleans as JSON text)."""
    if isinstance(v, str):
        return v
    if v is None or isinstance(v, (list, dict)):
        return None
    return _scalar(v)


def repo_of(args: dict[str, Any]) -> str | None:
    o, r = _as_str(args.get("owner")), _as_str(args.get("repo"))
    if o is not None and r is not None:
        return lower(f"{o}/{r}")
    return None


def known_label(p: Policy, call: dict[str, Any]) -> int | None:
    name = repo_of(call.get("arguments") or {})
    if name is None:
        return None
    for pat, label in p.repos:
        if glob(lower(pat), name):
            return label
    return None


def step(p: Policy, session: dict[str, Any], call: dict[str, Any]) -> dict[str, Any]:
    """The same fields the Lean worker returns (minus `theorem`)."""
    level, tainted = session.get("level", 0), session.get("tainted", False)
    m = first_match(p, call)
    if m is None:
        rule, action, read_level, dests, untrusted, high = None, "deny", p.top, [0], True, True
    else:
        i, r = m
        label = known_label(p, call)
        rule, action = i + 1, r.action
        read_level = (p.top if label is None else label) if r.reads else 0
        dests = [0 if label is None else label] if r.writes else []
        untrusted, high = r.untrusted, r.high_impact
    absorbed = {"level": max(level, read_level), "tainted": tainted or untrusted}
    if action == "deny":
        verdict, cause, nxt = "deny", ("rule" if rule else "no_rule"), session
    elif any(d < level for d in dests):
        verdict, cause, nxt = "deny", "leak", session
    elif action == "ask":
        verdict, cause, nxt = "ask", "rule", absorbed
    elif tainted and high:
        verdict, cause, nxt = "ask", "untrusted", absorbed
    else:
        verdict, cause, nxt = "allow", "allowed", absorbed
    return {
        "verdict": verdict,
        "cause": cause,
        "rule": rule,
        "next": {"level": nxt.get("level", 0), "tainted": nxt.get("tainted", False)},
        "class": {
            "readLevel": read_level,
            "dests": dests,
            "untrusted": untrusted,
            "highImpact": high,
        },
    }
