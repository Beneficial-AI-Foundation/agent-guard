#!/usr/bin/env python3
"""Checks every prerequisite for the phase 4 live run, and says what to do next.

    uv run scripts/phase4_preflight.py OWNER [--profile ~/agentguard-live]

Read-only: it creates nothing, changes nothing on GitHub, and never prints tokens.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

OK, WARN, FAIL = "✓", "⚠", "✗"
results: list[str] = []


def report(mark: str, text: str, fix: str = "") -> None:
    results.append(mark)
    print(f"{mark} {text}")
    if fix and mark != OK:
        print(f"    → {fix}")


def gh(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["gh", *args], capture_output=True, text=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("owner", help="org or user that owns demo-public and demo-private")
    ap.add_argument("--profile", default="~/agentguard-live")
    a = ap.parse_args()
    profile = Path(a.profile).expanduser()

    # 1. Tools
    for tool, why in (
        ("gh", "setup_test_repos.sh and the REST checks"),
        ("claude", "the automated real-agent prompts (optional)"),
    ):
        found = shutil.which(tool)
        mark = OK if found else (WARN if tool == "claude" else FAIL)
        report(
            mark,
            f"{tool} {'found' if found else 'not found'} ({why})",
            "install it" if not found else "",
        )
    worker = subprocess.run(
        [sys.executable, "-m", "agentguard", "version"], capture_output=True, text=True
    )
    report(OK if worker.returncode == 0 else FAIL, "AgentGuard and the Lean worker", "make proofs")

    # 2. GitHub CLI sign-in (used only by the setup script and the checks, never the agent)
    if shutil.which("gh"):
        signed = gh("auth", "status").returncode == 0
        report(
            OK if signed else FAIL,
            "gh is signed in" if signed else "gh is not signed in",
            "gh auth login --web",
        )

        # 3. Test repositories
        for name, want_private in (("demo-public", False), ("demo-private", True)):
            r = gh("repo", "view", f"{a.owner}/{name}", "--json", "visibility")
            if r.returncode != 0:
                report(
                    FAIL, f"{a.owner}/{name} not found", f"scripts/setup_test_repos.sh {a.owner}"
                )
                continue
            vis = json.loads(r.stdout)["visibility"].lower()
            good = (vis == "private") == want_private
            report(
                OK if good else FAIL,
                f"{a.owner}/{name} exists ({vis})",
                f"make {name} {'private' if want_private else 'public'}",
            )
        r = gh(
            "issue",
            "list",
            "-R",
            f"{a.owner}/demo-public",
            "--search",
            "CI is broken",
            "--json",
            "number",
        )
        poisoned = r.returncode == 0 and json.loads(r.stdout or "[]")
        report(
            OK if poisoned else FAIL,
            "poisoned issue 'CI is broken' in demo-public",
            f"scripts/setup_test_repos.sh {a.owner} (on fresh repos)",
        )

    # 4. GitHub App client ID
    env_file = profile / ".env"
    client_id = os.environ.get("AGENTGUARD_GITHUB_CLIENT_ID", "")
    if not client_id and env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("AGENTGUARD_GITHUB_CLIENT_ID="):
                client_id = line.split("=", 1)[1].strip()
    report(
        OK if client_id else FAIL,
        "GitHub App client ID set" if client_id else "no GitHub App client ID",
        f"register the App (docs/phase4.md step 2), put its Client ID in {env_file}",
    )
    if client_id:
        # The device-code endpoint answers without auth; it shows whether device flow is on.
        req = urllib.request.Request(
            "https://github.com/login/device/code",
            data=f"client_id={client_id}".encode(),
            headers={"Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = json.loads(resp.read())
        except urllib.error.URLError as e:
            body = {"error": str(e)}
        on = "device_code" in body
        report(
            OK if on else FAIL,
            "device flow enabled for that App"
            if on
            else f"device flow refused: {body.get('error_description') or body.get('error')}",
            "App settings → tick 'Enable Device Flow'",
        )

    # 5. Profile and sign-in
    if not (profile / "rules.yaml").exists():
        report(
            FAIL,
            f"no profile at {profile}",
            f"agentguard init github --profile {profile} --no-login",
        )
    else:
        doc = subprocess.run(
            [sys.executable, "-m", "agentguard", "doctor", "--profile", str(profile)],
            capture_output=True,
            text=True,
        )
        signed_in = "signed in" in doc.stdout and "not signed in" not in doc.stdout
        report(
            OK if signed_in else FAIL,
            "AgentGuard is signed in to GitHub",
            f"agentguard login {profile}",
        )

    fails = results.count(FAIL)
    print(
        f"\n{'Ready for phase 4.' if not fails else f'{fails} thing(s) to do first.'}"
        "  Runbook: docs/phase4.md"
    )
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
