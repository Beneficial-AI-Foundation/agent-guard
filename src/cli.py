"""The `agentguard` command.

init · login · logout · connect · doctor · try · check · serve · stdio · demo · report
· verify · version
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from . import __version__
from .errors import AgentGuardError, RulesError
from .settings import Mode, Settings, default_profile


def say(msg: str = "") -> None:
    """Human output goes to stderr, so stdout stays clean for the stdio MCP transport."""
    print(msg, file=sys.stderr, flush=True)


def profile_dir(arg: str | None) -> Path:
    if arg is None:
        return default_profile()
    p = Path(arg).expanduser()
    return p if (p.is_dir() or "/" in arg or arg.startswith(".")) else default_profile(arg)


# version


async def _worker_info() -> dict[str, Any] | None:
    from .monitor.worker import Worker
    from .proxy.server import file_hash

    try:
        async with Worker() as w:
            info = await w.info()
            info["hash"] = file_hash(w.binary)
            info["path"] = str(w.binary)
            return info
    except AgentGuardError:
        return None


def cmd_version(args: argparse.Namespace) -> int:
    print(f"agentguard {__version__}")
    info = asyncio.run(_worker_info())
    if info is None:
        print("guard-worker: not found")
        return 1
    print(f"guard-worker {info['version']}  build {info['hash']}  ({info['path']})")
    print(f"theorems ({len(info['theorems'])}): " + ", ".join(info["theorems"]))
    return 0


# check


def cmd_check(args: argparse.Namespace) -> int:
    """Validates a rule file with Lean (the same check the gateway does)."""
    from .monitor.worker import Worker
    from .profile import rules

    path = Path(args.rules) if args.rules else profile_dir(args.profile) / "rules.yaml"

    async def run() -> int:
        policy = rules.load(path)
        async with Worker() as w:
            n = await w.load(policy)
        print(f"✓ {path}: {n} rules, labels {' < '.join(policy['labels'])}")
        return 0

    try:
        return asyncio.run(run())
    except RulesError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1


# serve / stdio


def _port_free(host: str, port: int) -> bool:
    with socket.socket() as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def _free_port(host: str, preferred: int) -> int:
    if _port_free(host, preferred):
        return preferred
    with socket.socket() as s:
        s.bind((host, 0))
        return int(s.getsockname()[1])


async def _uvicorn(app: Any, host: str, port: int) -> None:
    import uvicorn

    config = uvicorn.Config(app, host=host, port=port, log_level="warning", access_log=False)
    server = uvicorn.Server(config)
    await server.serve()


def _settings(args: argparse.Namespace) -> Settings:
    s = Settings.from_env()
    changes: dict[str, Any] = {}
    if getattr(args, "mode", None):
        changes["mode"] = Mode(args.mode)
    if getattr(args, "port", None):
        changes["gateway_port"] = args.port
    if getattr(args, "console_port", None):
        changes["console_port"] = args.console_port
    if getattr(args, "host", None):
        changes["gateway_host"] = args.host
    return Settings(**{**s.__dict__, **changes})


async def _run(args: argparse.Namespace, transport: str) -> None:
    from .auth import auth_factory
    from .auth.keyring_store import TokenStore
    from .console.app import make_app
    from .profile import loader
    from .proxy.server import Gateway, http_app, serve_stdio

    settings = _settings(args)
    profile = loader.load(profile_dir(args.profile))
    audit = profile.folder / "audit.jsonl"
    auth = auth_factory(profile.name, TokenStore())
    console_token = secrets.token_urlsafe(16)
    async with Gateway.open(profile, settings, audit_path=audit, auth=auth) as gw:
        tasks = [asyncio.create_task(gw.watch_rules())]
        console = None
        if not args.no_console:
            host = settings.console_host
            port = _free_port(host, settings.console_port)
            console = f"http://127.0.0.1:{port}/#token={console_token}"
            tasks.append(asyncio.create_task(_uvicorn(make_app(gw, console_token), host, port)))
        say(f"AgentGuard {__version__} · profile {profile.folder} · mode {settings.mode.value}")
        say(
            f"  guarding {', '.join(s.name for s in profile.servers)}: "
            f"{len(gw.upstreams.routes)} tools · {len(profile.policy.get('rules', []))} rules"
        )
        if console:
            say(f"  console  {console}")
        say(f"  audit    {audit}")
        try:
            if transport == "stdio":
                await serve_stdio(gw)
            else:
                token = os.environ.get("AGENTGUARD_GATEWAY_TOKEN") or None
                url = f"http://{settings.gateway_host}:{settings.gateway_port}/mcp"
                say(f"  gateway  {url}" + ("  (bearer token required)" if token else ""))
                await _uvicorn(http_app(gw, token), settings.gateway_host, settings.gateway_port)
        finally:
            for t in tasks:
                t.cancel()
            for t in tasks:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await t


def cmd_serve(args: argparse.Namespace) -> int:
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_run(args, "http"))
    return 0


def cmd_stdio(args: argparse.Namespace) -> int:
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_run(args, "stdio"))
    return 0


# login / logout


def cmd_login(args: argparse.Namespace) -> int:
    import httpx2

    from .auth import account, github_client_id, is_github
    from .auth.device_flow import device_login, github_login_name
    from .auth.keyring_store import TokenStore
    from .profile import loader

    profile = loader.load(profile_dir(args.profile))
    store = TokenStore()
    servers = (
        [profile.server(args.server)]
        if args.server
        else [s for s in profile.servers if s.kind == "http" and s.auth == "oauth"]
    )
    if not servers:
        say("Nothing to sign in to: every server uses a local command or a token from .env.")
        return 0

    async def run() -> None:
        for cfg in servers:
            acct = account(profile.name, cfg.name)
            if is_github(cfg):
                client_id = github_client_id()
                if not client_id:
                    raise AgentGuardError(
                        "AGENTGUARD_GITHUB_CLIENT_ID is not set: register a GitHub App with "
                        "device flow enabled (see docs/quickstart.md) and set its client ID"
                    )

                def show(url: str, code: str) -> None:
                    say(f"Open {url} and enter code  {code}")

                async with httpx2.AsyncClient(timeout=30) as http:
                    token = await device_login(client_id, scope=args.scope, show=show, http=http)
                    token.login = await github_login_name(token, http, "https://api.github.com")
                store.set(acct, token.to_json())
                who = f"@{token.login}" if token.login else "GitHub"
                say(
                    f"✓ Signed in as {who} (scopes: {token.scope or 'app permissions'}); "
                    f"token stored in the {store.backend} store"
                )
            else:
                from mcp import Client
                from mcp.client.streamable_http import streamable_http_client

                from .auth.oauth import provider

                assert cfg.url is not None
                oauth = provider(cfg.url, store, acct, interactive=True, say=say)
                http = httpx2.AsyncClient(auth=oauth, timeout=60)
                async with Client(streamable_http_client(cfg.url, http_client=http)) as c:
                    await c.list_tools()
                say(f"✓ Signed in to {cfg.name}; token stored in the {store.backend} store")

    asyncio.run(run())
    return 0


def cmd_logout(args: argparse.Namespace) -> int:
    from .auth import account
    from .auth.keyring_store import TokenStore
    from .profile import loader

    profile = loader.load(profile_dir(args.profile))
    store = TokenStore()
    for cfg in profile.servers:
        if not args.server or cfg.name == args.server:
            store.delete(account(profile.name, cfg.name))
            say(f"Signed out of {cfg.name}")
    return 0


# verify


def cmd_verify(args: argparse.Namespace) -> int:
    """Re-checks the proofs from source (needs a checkout and Lean)."""
    root = Path(__file__).resolve().parent.parent
    script = root / "scripts" / "check_proofs.sh"
    if not script.exists() or shutil.which("lake") is None:
        say(
            "verify needs a source checkout and Lean (elan): git clone the repository and run "
            "scripts/check_proofs.sh"
        )
        return 2
    return subprocess.call([str(script)])  # noqa: S603


# init


def cmd_init(args: argparse.Namespace) -> int:
    from .demo import template_dir

    template = template_dir(args.template)
    dest = Path(args.profile).expanduser() if args.profile else default_profile(args.template)
    if dest.exists() and any(dest.iterdir()) and not args.force:
        raise AgentGuardError(f"{dest} already exists (use --force to overwrite the templates)")
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("mcp.json", "rules.yaml", ".env.example"):
        shutil.copy2(template / name, dest / name)
    env = dest / ".env"
    if not env.exists():
        shutil.copy2(template / ".env.example", env)
        env.chmod(0o600)
    say(f"✓ Created {dest}")
    say("    mcp.json    the servers to guard (paste from VS Code's mcp.json to change them)")
    say("    rules.yaml  what agents may do (docs/rules.md)")
    say("    .env        secrets, never committed")
    if not args.no_login:
        from .profile import loader

        profile = loader.load(dest)
        if any(s.kind == "http" and s.auth == "oauth" for s in profile.servers):
            ns = argparse.Namespace(profile=str(dest), server=None, scope="")
            try:
                cmd_login(ns)
            except AgentGuardError as e:
                say(f"! Sign-in skipped: {e}")
                say(f"  Run `agentguard login {dest}` when ready.")
    say("Next: agentguard connect vscode   (or claude-code, cursor)")
    return 0


# try


def parse_call(text: str) -> tuple[str, dict[str, Any]]:
    """`push_files owner=octo repo=r branch=main files='[{"path": "a"}]'`"""
    import shlex

    words = shlex.split(text)
    if not words:
        raise AgentGuardError("give a tool name, then key=value arguments")
    args: dict[str, Any] = {}
    for w in words[1:]:
        key, sep, value = w.partition("=")
        if not sep:
            raise AgentGuardError(f"{w!r}: arguments are key=value")
        try:
            args[key] = json.loads(value)
        except ValueError:
            args[key] = value
    return words[0], args


def cmd_try(args: argparse.Namespace) -> int:
    """Shows what the rules decide, without an agent and without calling anything."""
    from .monitor.worker import SessionState, Worker
    from .profile import loader

    profile = loader.load(profile_dir(args.profile))
    labels: list[str] = list(profile.policy.get("labels", []))

    async def decide(call: str) -> int:
        tool, call_args = parse_call(call)
        server, _, name = tool.replace("__", ".").rpartition(".")
        if not server:
            server = profile.servers[0].name
        level = labels.index(args.level) if args.level else 0
        session = SessionState(level=level, tainted=args.tainted)
        async with Worker() as w:
            await w.load(profile.policy)
            d = await w.step(session, {"server": server, "tool": name, "arguments": call_args})
        rule = f"rule {d.rule}" if d.rule else "no rule"
        why = {
            "rule": rule,
            "no_rule": "no rule applies",
            "leak": "would leak",
            "untrusted": "after outsider text",
            "allowed": rule,
            "error": d.error or "",
        }
        print(
            f"{d.verdict.upper():6} {why.get(d.cause, d.cause)}"
            + (f" · theorem {d.theorem}" if d.theorem else "")
        )
        if d.rule:
            r = profile.policy["rules"][d.rule - 1]
            print(f"       {json.dumps(r, ensure_ascii=False)}")
        return 0

    async def listing() -> int:
        from contextlib import AsyncExitStack

        from .auth import auth_factory
        from .auth.keyring_store import TokenStore
        from .monitor.reference import glob
        from .proxy.upstream import Upstreams

        async with AsyncExitStack() as stack:
            up = Upstreams(profile.servers, auth=auth_factory(profile.name, TokenStore()))
            await up.start(stack)
            rules = profile.policy.get("rules", [])
            print(
                f"Connected to {', '.join(s.name for s in profile.servers)} "
                f"({len(up.routes)} tools) · {len(rules)} rules"
            )
            print(f"{'TOOL':34} {'WHAT THE RULES SAY'}")
            for exposed, route in sorted(up.routes.items()):
                full = f"{route.server}.{route.tool}"
                parts = []
                for i, r in enumerate(rules, 1):
                    if glob(r["tool"], full):  # display only; Lean decides real calls
                        when = " ".join(f"{k}={v}" for k, v in (r.get("when") or {}).items())
                        parts.append(f"{r['action']}{' if ' + when if when else ''} (#{i})")
                        if not r.get("when"):
                            break
                print(f"{exposed:34} {' · '.join(parts) or 'DENY (no rule)'}")
        return 0

    return asyncio.run(decide(args.call) if args.call else listing())


# demo


def cmd_demo(args: argparse.Namespace) -> int:
    from .demo import run_all

    results = asyncio.run(run_all(args.template, only=args.story))
    failed = 0
    for r in results:
        mark = "✓" if r.ok else "✗"
        print(f"\n{mark} {r.name}  {r.title}" + (f"  · {r.theorem}" if r.theorem else ""))
        print(f"  {r.summary}")
        for s in r.steps:
            sm = "✓" if s.ok else "✗"
            rule = f"rule {s.rule}" if s.rule else ""
            person = f" → person {s.person}s" if s.person else ""
            print(
                f"  {sm} {s.call:28} {str(s.got).upper():6} {rule}{person}"
                + ("" if s.ok else f"   (expected {s.expect})")
            )
            if s.message.startswith("Blocked by AgentGuard"):
                print(f"      “{s.message}”")
        for says, ok in r.checks:
            print(f"  {'✓' if ok else '✗'} {says}")
        failed += not r.ok
    print(f"\n{len(results) - failed}/{len(results)} stories behaved as expected.")
    return 1 if failed else 0


# report


def cmd_report(args: argparse.Namespace) -> int:
    from collections import Counter

    path = Path(args.audit) if args.audit else profile_dir(args.profile) / "audit.jsonl"
    if not path.exists():
        raise AgentGuardError(f"{path} not found (nothing has run yet)")
    events = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    calls = [e for e in events if e.get("tool")]
    if args.last and calls:
        start = max(i for i, e in enumerate(events) if e.get("kind") == "start")
        calls = [e for e in events[start:] if e.get("tool")]
    outcomes = Counter(e.get("outcome") for e in calls)
    print(f"{path}: {len(calls)} tool calls in {len({e.get('session') for e in calls})} session(s)")
    for outcome, n in outcomes.most_common():
        print(f"  {n:5}  {outcome}")
    blocked = [e for e in calls if e.get("outcome") in ("denied", "rejected", "timeout")]
    if blocked:
        print("\nBlocked:")
        for e in blocked:
            why = e.get("cause") if e.get("outcome") == "denied" else e.get("outcome")
            rule = f" rule {e['rule']}" if e.get("rule") else ""
            print(
                f"  {e['tool']:28} {why}{rule}" + (f" · {e['theorem']}" if e.get("theorem") else "")
            )
    asked = [e for e in calls if e.get("outcome") in ("approved", "rejected", "timeout")]
    if asked:
        print(
            f"\nPeople answered {len(asked)} request(s): "
            + ", ".join(f"{k} {v}" for k, v in Counter(e["outcome"] for e in asked).items())
        )
    rejected = [e for e in events if e.get("kind") == "rules" and e.get("outcome") == "rejected"]
    if rejected:
        print(f"\n{len(rejected)} rule-file change(s) were rejected and not loaded.")
    return 0


# connect / doctor


def cmd_connect(args: argparse.Namespace) -> int:
    from .clients import claude_code, cursor, vscode
    from .clients.base import ConfigFile, agentguard_entry
    from .profile import loader

    profile = loader.load(profile_dir(args.profile))
    mods = {"vscode": vscode, "cursor": cursor, "claude-code": claude_code}
    mod = mods[args.client]
    workspace = Path(args.workspace).expanduser() if args.workspace else None
    if args.client == "claude-code" and workspace is None:
        if claude_code.cli() is None:
            raise AgentGuardError(
                "the claude CLI isn't on PATH; use --workspace DIR to write "
                "that project's .mcp.json instead"
            )
        cfg = ConfigFile.read(claude_code.user_config(), claude_code.KEY)
        backups = profile.folder / "disabled-servers.json"
        direct = cfg.direct(profile.servers)
        if args.dry_run:
            say(f"Would add agentguard (user scope) and remove {direct or 'nothing'}")
            return 0
        if direct:
            saved = {n: cfg.servers[n] for n in direct}
            backups.write_text(json.dumps(saved, indent=2) + "\n", encoding="utf-8")
            for n in direct:
                claude_code.remove_user(n)
        claude_code.add_user(agentguard_entry(profile.folder))
        say(
            "✓ Claude Code (user scope) now uses AgentGuard"
            + (f"; removed {', '.join(direct)} (saved to {backups})" if direct else "")
        )
        return 0
    path = mod.workspace_config(workspace) if workspace else mod.user_config()
    cfg = ConfigFile.read(path, mod.KEY)
    if args.dry_run:
        aside = cfg.direct(profile.servers) or "nothing"
        say(f"Would add agentguard to {path} and set aside {aside}")
        return 0
    moved, backup = cfg.connect(profile.folder, profile.servers)
    say(f"✓ {path} now uses AgentGuard")
    if moved:
        say(
            f'  Set aside {", ".join(moved)} (under "agentguardDisabled"), so the agent can\'t '
            "reach them directly"
        )
    if backup:
        say(f"  Backup: {backup} (comments in the original are kept only there)")
    say("  Reload the window (VS Code: Developer: Reload Window) and run `agentguard doctor`.")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    from .doctor import Finding, check_clients, check_shell, check_sign_in
    from .monitor.worker import Worker
    from .profile import loader

    findings: list[Finding] = []
    info = asyncio.run(_worker_info())
    if info is None:
        findings.append(Finding("fail", "guard-worker not found"))
    else:
        findings.append(
            Finding("ok", f"decision worker {info['hash']} · {len(info['theorems'])} theorems")
        )
    try:
        profile = loader.load(profile_dir(args.profile))
    except AgentGuardError as e:
        findings.append(Finding("fail", str(e)))
        profile = None
    if profile is not None:

        async def check_rules() -> int:
            async with Worker() as w:
                return await w.load(profile.policy)

        try:
            n = asyncio.run(check_rules())
            findings.append(Finding("ok", f"profile {profile.folder}: {n} rules accepted"))
        except AgentGuardError as e:
            findings.append(Finding("fail", f"rules: {e}"))
        findings += check_sign_in(profile)
        findings += check_clients(profile, Path.cwd())
    findings += check_shell()
    for f in findings:
        print(f"{f.mark} {f.text}")
    return 1 if any(f.level == "fail" for f in findings) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentguard",
        description="MCP gateway with allow / ask / deny decisions proved in Lean 4.",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    sub.add_parser("version", help="print versions, the worker build and its theorems")

    p = sub.add_parser("check", help="validate a rule file with Lean")
    p.add_argument("--profile", help="profile name or folder (default: ~/.agentguard/github)")
    p.add_argument("--rules", help="a rules.yaml file to check instead")

    for name, help_ in (
        ("serve", "run the HTTP gateway and the console"),
        ("stdio", "run as a stdio MCP server (for an agent's mcp.json)"),
    ):
        p = sub.add_parser(name, help=help_)
        p.add_argument("--profile", help="profile name or folder (default: ~/.agentguard/github)")
        p.add_argument("--mode", choices=[m.value for m in Mode])
        p.add_argument("--console-port", type=int)
        p.add_argument("--no-console", action="store_true", help="don't start the console")
        if name == "serve":
            p.add_argument("--host")
            p.add_argument("--port", type=int)

    p = sub.add_parser("login", help="sign in to the profile's remote servers")
    p.add_argument("profile", nargs="?")
    p.add_argument("server", nargs="?")
    p.add_argument("--scope", default="", help="OAuth scopes (OAuth Apps only, e.g. repo)")

    p = sub.add_parser("logout", help="forget stored sign-ins")
    p.add_argument("profile", nargs="?")
    p.add_argument("server", nargs="?")

    sub.add_parser("verify", help="re-check the Lean proofs from source")

    p = sub.add_parser("init", help="create a profile folder from a template, then sign in")
    p.add_argument("template", nargs="?", default="github")
    p.add_argument("--profile", help="folder to create (default: ~/.agentguard/<template>)")
    p.add_argument("--force", action="store_true")
    p.add_argument("--no-login", action="store_true")

    p = sub.add_parser("try", help="see what the rules decide, without an agent")
    p.add_argument("call", nargs="?", help='e.g. "push_files owner=o repo=r branch=main"')
    p.add_argument("--profile")
    p.add_argument("--level", help="label the session has already read (e.g. private)")
    p.add_argument("--tainted", action="store_true", help="the session read outsider text")

    p = sub.add_parser("demo", help="run the demo stories offline against a mock server")
    p.add_argument("story", nargs="?", help="only stories whose name starts with this")
    p.add_argument("--template", default="github")

    p = sub.add_parser("report", help="summarise the audit log")
    p.add_argument("--profile")
    p.add_argument("--audit", help="an audit.jsonl file")
    p.add_argument("--last", action="store_true", help="only since the last start")

    p = sub.add_parser("connect", help="point an agent's MCP config at AgentGuard")
    p.add_argument("client", choices=["vscode", "claude-code", "cursor"])
    p.add_argument("--profile")
    p.add_argument("--workspace", help="edit this project's config instead of the user's")
    p.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("doctor", help="check AgentGuard works and nothing goes around it")
    p.add_argument("--profile")
    return parser


COMMANDS = {
    "version": cmd_version,
    "check": cmd_check,
    "serve": cmd_serve,
    "stdio": cmd_stdio,
    "login": cmd_login,
    "logout": cmd_logout,
    "verify": cmd_verify,
    "init": cmd_init,
    "try": cmd_try,
    "demo": cmd_demo,
    "report": cmd_report,
    "connect": cmd_connect,
    "doctor": cmd_doctor,
}


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 2
    try:
        return COMMANDS[args.command](args)
    except AgentGuardError as e:
        say(f"error: {e}")
        return 1
