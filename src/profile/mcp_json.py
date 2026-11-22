"""Reads `mcp.json` as VS Code writes it (`servers`) or as Claude and Cursor write it
(`mcpServers`). Comments and trailing commas are allowed, as in VS Code."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from ..errors import ProfileError
from .env import load_dotenv, substitute_all


@dataclass(frozen=True)
class ServerConfig:
    name: str
    kind: Literal["stdio", "http"]
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    cwd: str | None = None
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


def strip_jsonc(text: str) -> str:
    """Removes // and /* */ comments and trailing commas, leaving strings alone."""
    out: list[str] = []
    i, n = 0, len(text)
    in_str = False
    while i < n:
        ch = text[i]
        if in_str:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_str = False
            i += 1
        elif ch == '"':
            in_str = True
            out.append(ch)
            i += 1
        elif text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
        elif ch == ",":
            j = i + 1
            while j < n and text[j] in " \t\r\n":
                j += 1
            if j < n and text[j] in "}]":
                i += 1
            else:
                out.append(ch)
                i += 1
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def parse(text: str) -> dict[str, Any]:
    try:
        data = json.loads(strip_jsonc(text))
    except json.JSONDecodeError as e:
        raise ProfileError(f"mcp.json: {e}") from e
    if not isinstance(data, dict):
        raise ProfileError("mcp.json must be a JSON object")
    servers = data.get("servers", data.get("mcpServers"))
    if not isinstance(servers, dict):
        raise ProfileError(
            'mcp.json needs a "servers" (VS Code) or "mcpServers" (Claude, Cursor) object'
        )
    return servers


def is_agentguard(name: str, raw: Mapping[str, Any]) -> bool:
    """AgentGuard's own entry, if someone pasted a whole config: skipped to avoid a loop."""
    cmd = str(raw.get("command", ""))
    return name == "agentguard" or Path(cmd).name in ("agentguard", "agentguard.exe")


def server_from(
    name: str, raw: Mapping[str, Any], env: Mapping[str, str], folder: Path
) -> ServerConfig:
    if not isinstance(raw, Mapping):
        raise ProfileError(f"mcp.json: server {name!r} must be an object")
    builtins = {"workspaceFolder": str(folder), "userHome": str(Path.home())}
    merged = dict(env)
    if "envFile" in raw:
        env_file = Path(str(substitute_all(raw["envFile"], env, builtins))).expanduser()
        merged |= load_dotenv(env_file if env_file.is_absolute() else folder / env_file)
    r = substitute_all(dict(raw), merged, builtins)
    kind = r.get("type") or ("stdio" if "command" in r else "http" if "url" in r else None)
    if kind == "stdio":
        if not isinstance(r.get("command"), str):
            raise ProfileError(f"mcp.json: server {name!r} needs a command")
        return ServerConfig(
            name=name,
            kind="stdio",
            command=r["command"],
            args=[str(a) for a in r.get("args", [])],
            env={k: str(v) for k, v in r.get("env", {}).items()},
            cwd=r.get("cwd"),
        )
    if kind in ("http", "streamable-http", "streamableHttp"):
        if not isinstance(r.get("url"), str):
            raise ProfileError(f"mcp.json: server {name!r} needs a url")
        headers = {k: str(v) for k, v in r.get("headers", {}).items()}
        return ServerConfig(name=name, kind="http", url=r["url"], headers=headers)
    if kind == "sse":
        raise ProfileError(
            f"mcp.json: server {name!r} uses the old SSE transport; use its HTTP URL"
        )
    raise ProfileError(f"mcp.json: server {name!r} needs a command (local) or a url (remote)")


def load(path: Path, env: Mapping[str, str]) -> list[ServerConfig]:
    if not path.exists():
        raise ProfileError(f"{path} not found")
    servers = parse(path.read_text(encoding="utf-8"))
    out = [
        server_from(name, raw, env, path.parent)
        for name, raw in servers.items()
        if not is_agentguard(name, raw)
    ]
    for s in out:
        if not s.name or "." in s.name or "__" in s.name:
            raise ProfileError(f"mcp.json: server name {s.name!r} can't contain '.' or '__'")
    if not out:
        raise ProfileError(f"{path}: no servers to guard")
    return out
