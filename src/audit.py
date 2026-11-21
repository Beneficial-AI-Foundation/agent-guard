"""The audit log (`audit.jsonl`, one line per decision) and the in-memory feed the
console shows.

Secrets never reach the log: values under secret-looking keys are replaced by a
fingerprint, well-known token formats are replaced wherever they appear, and long
text (file contents, comment bodies) is cut to a prefix plus a fingerprint.

Schema versioning: fields may be added freely; renaming or removing one bumps
`SCHEMA_VERSION`.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

_SECRET_KEY = re.compile(
    r"(token|secret|passw|authorization|api[_-]?key|private[_-]?key|credential|cookie)", re.I
)
_TOKEN = re.compile(
    r"(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}"
    r"|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)"
)
_LONG = 200
#: `DEPLOY_KEY=…`, `password: …` inside free text (comment bodies, file contents).
_ASSIGN = re.compile(
    r"(?i)\b([A-Z0-9_.-]*(?:key|token|secret|passw(?:or)?d|credential)[A-Z0-9_.-]*)"
    r"(\s*[=:]\s*)([^\s\"',;]+)"
)


def fingerprint_all(value: Any) -> Any:
    """Every string replaced by its fingerprint (structure and keys kept). Used for calls
    denied as leaks, whose payload is presumed to be private data."""
    if isinstance(value, dict):
        return {k: fingerprint_all(v) for k, v in value.items()}
    if isinstance(value, list):
        return [fingerprint_all(v) for v in value]
    if isinstance(value, str):
        return f"<{len(value)} chars {fingerprint(value)}>"
    return value


def fingerprint(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()[:12]


def redact(value: Any, key: str | None = None) -> Any:
    """A copy of `value` that is safe to log."""
    if isinstance(value, dict):
        return {k: redact(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, key) for v in value]
    if isinstance(value, str):
        if key is not None and _SECRET_KEY.search(key):
            return f"<redacted {fingerprint(value)}>"
        value = _TOKEN.sub(lambda m: f"<token {fingerprint(m.group(0))}>", value)
        value = _ASSIGN.sub(
            lambda m: f"{m.group(1)}{m.group(2)}<redacted {fingerprint(m.group(3))}>", value
        )
        if len(value) > _LONG:
            return f"{value[:80]}… <{len(value)} chars, {fingerprint(value)}>"
    return value


class AuditLog:
    """Appends one JSON line per event. Thread- and task-safe."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self._lock = threading.Lock()
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch(mode=0o600, exist_ok=True)

    def write(self, event: dict[str, Any]) -> None:
        if self.path is None:
            return
        line = json.dumps({"v": SCHEMA_VERSION, **event}, ensure_ascii=False)
        with self._lock, self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


class EventFeed:
    """The last events, numbered, for the console's live feed."""

    def __init__(self, size: int = 1000) -> None:
        self._events: deque[dict[str, Any]] = deque(maxlen=size)
        self._seq = 0

    def add(self, event: dict[str, Any]) -> dict[str, Any]:
        self._seq += 1
        event = {"seq": self._seq, "time": event.get("time", time.time()), **event}
        self._events.append(event)
        return event

    def since(self, seq: int) -> list[dict[str, Any]]:
        return [e for e in self._events if e["seq"] > seq]

    @property
    def last(self) -> int:
        return self._seq
