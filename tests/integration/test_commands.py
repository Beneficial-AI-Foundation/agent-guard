"""init, try, connect, doctor, report and demo as a person runs them."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

GITHUB_URL = "https://api.githubcopilot.com/mcp/"


def run(
    *args: str, cwd: Path | None = None, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "agentguard", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        timeout=120,
    )


@pytest.fixture
def env(tmp_path: Path, worker_binary: Path) -> dict[str, str]:
    e = {k: v for k, v in os.environ.items() if k not in ("GITHUB_TOKEN", "GH_TOKEN")}
    return {
        **e,
        "AGENTGUARD_HOME": str(tmp_path / "home"),
        "AGENTGUARD_WORKER": str(worker_binary),
        "AGENTGUARD_TOKEN_STORE": "memory",
        "HOME": str(tmp_path / "userhome"),
    }


@pytest.fixture
def profile(tmp_path: Path, env: dict[str, str]) -> Path:
    r = run("init", "--no-login", env=env)
    assert r.returncode == 0, r.stderr
    return tmp_path / "home" / "github"


def test_init(profile: Path, env: dict[str, str]) -> None:
    assert {p.name for p in profile.iterdir()} == {"mcp.json", "rules.yaml", ".env.example", ".env"}
    assert oct((profile / ".env").stat().st_mode & 0o777) == "0o600"
    again = run("init", "--no-login", env=env)
    assert again.returncode == 1 and "already exists" in again.stderr


def test_try_single_calls(profile: Path, env: dict[str, str]) -> None:
    r = run("try", "push_files owner=o repo=demo-public branch=main", env=env)
    assert (
        r.returncode == 0 and r.stdout.startswith("DENY") and "deny_rule_always_denies" in r.stdout
    )
    r = run(
        "try",
        'push_files owner=o repo=demo-public branch=fix files=[{"path":".github/x"}]',
        env=env,
    )
    assert r.stdout.startswith("ASK")
    r = run(
        "try",
        "add_issue_comment owner=o repo=demo-public issue_number=1",
        "--level",
        "private",
        env=env,
    )
    assert r.stdout.startswith("DENY") and "would leak" in r.stdout
    r = run("try", "github.create_pull_request owner=o repo=demo-public", "--tainted", env=env)
    assert r.stdout.startswith("ASK") and "no_untrusted_steering" in r.stdout


def test_connect_and_doctor(tmp_path: Path, profile: Path, env: dict[str, str]) -> None:
    ws = tmp_path / "project"
    (ws / ".vscode").mkdir(parents=True)
    config = ws / ".vscode" / "mcp.json"
    config.write_text(
        '{\n  // my servers\n  "servers": {\n'
        f'    "github": {{"type": "http", "url": "{GITHUB_URL}"}},\n'
        '    "other": {"command": "other-server"},\n  }\n}\n'
    )
    before = run("doctor", cwd=ws, env=env)
    assert "reaches a guarded server directly" in before.stdout
    assert "not signed in" in before.stdout and before.returncode == 1

    r = run("connect", "vscode", "--workspace", str(ws), env=env)
    assert r.returncode == 0, r.stderr
    data = json.loads(config.read_text())
    assert set(data["servers"]) == {"other", "agentguard"}
    assert data["agentguardDisabled"]["github"]["url"] == GITHUB_URL
    assert data["servers"]["agentguard"]["args"][-3:] == ["stdio", "--profile", str(profile)]
    assert list(ws.glob(".vscode/mcp.json.agentguard-backup-*"))

    after = run("doctor", cwd=ws, env=env)
    assert "uses AgentGuard" in after.stdout and "directly" not in after.stdout
    assert "10 theorems" in after.stdout and "35 rules accepted" in after.stdout


def test_report(tmp_path: Path, env: dict[str, str]) -> None:
    audit = tmp_path / "audit.jsonl"
    events = [
        {"kind": "start", "outcome": "started"},
        {
            "tool": "merge_pull_request",
            "session": "s",
            "outcome": "denied",
            "cause": "rule",
            "rule": 31,
            "theorem": "deny_rule_always_denies",
        },
        {"tool": "push_files", "session": "s", "outcome": "rejected"},
        {"tool": "push_files", "session": "s", "outcome": "approved"},
        {"tool": "get_me", "session": "s", "outcome": "allowed"},
    ]
    audit.write_text("".join(json.dumps(e) + "\n" for e in events))
    r = run("report", "--audit", str(audit), env=env)
    assert r.returncode == 0
    assert "4 tool calls in 1 session(s)" in r.stdout
    assert "merge_pull_request" in r.stdout and "rule 31" in r.stdout
    assert "People answered 2 request(s)" in r.stdout


def test_demo_command(env: dict[str, str]) -> None:
    r = run("demo", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "6/6 stories behaved as expected." in r.stdout
