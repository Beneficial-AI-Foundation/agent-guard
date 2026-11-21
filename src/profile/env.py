"""`.env` files and `${VAR}` / `${env:VAR}` / `${input:id}` substitution, as in VS Code."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..errors import ProfileError

_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_.-]*)\s*=\s*(.*?)\s*$")
_VAR = re.compile(r"\$\{([^}]*)\}")


def parse_dotenv(text: str) -> dict[str, str]:
    """`KEY=value` lines; `#` comments; optional `export`; single or double quotes."""
    out: dict[str, str] = {}
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _LINE.match(line)
        if not m:
            raise ProfileError(f".env line {n}: expected KEY=value")
        key, value = m.group(1), m.group(2)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
            if raw.strip().split("=", 1)[1].strip().startswith('"'):
                value = value.replace("\\n", "\n").replace('\\"', '"')
        else:
            value = re.sub(r"\s+#.*$", "", value)
        out[key] = value
    return out


def load_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return parse_dotenv(path.read_text(encoding="utf-8"))


def substitute(value: str, env: Mapping[str, str], builtins: Mapping[str, str]) -> str:
    """Replaces `${VAR}`, `${env:VAR}` and `${input:id}` from `env`, and VS Code
    variables like `${workspaceFolder}` from `builtins`. A missing variable is an error."""

    def repl(m: re.Match[str]) -> str:
        ref = m.group(1)
        if ref in builtins:
            return builtins[ref]
        kind, _, name = ref.partition(":")
        if not name:
            kind, name = "env", ref
        if kind == "env":
            if name in env:
                return env[name]
            raise ProfileError(f"${{{ref}}}: {name} is not set (add it to the profile's .env)")
        if kind == "input":
            for candidate in (name, name.upper(), name.upper().replace("-", "_")):
                if candidate in env:
                    return env[candidate]
            raise ProfileError(
                f"${{{ref}}}: AgentGuard can't prompt for inputs; add {name.upper()}=… to .env"
            )
        raise ProfileError(f"${{{ref}}}: unsupported variable")

    return _VAR.sub(repl, value)


def substitute_all(obj: Any, env: Mapping[str, str], builtins: Mapping[str, str]) -> Any:
    """`substitute` applied to every string inside lists and dicts."""
    if isinstance(obj, str):
        return substitute(obj, env, builtins)
    if isinstance(obj, list):
        return [substitute_all(x, env, builtins) for x in obj]
    if isinstance(obj, dict):
        return {k: substitute_all(v, env, builtins) for k, v in obj.items()}
    return obj
