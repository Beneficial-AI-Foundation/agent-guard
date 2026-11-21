"""Where sign-in tokens live: the OS keychain, or an encrypted file (Docker), never logs.

`AGENTGUARD_TOKEN_STORE` picks the backend: `keyring` (default when the OS has a
keychain), `file` (encrypted with the Fernet key in `AGENTGUARD_TOKEN_KEY`), or
`memory` (tests).
"""

from __future__ import annotations

import contextlib
import json
import os
import threading
from pathlib import Path
from typing import Any

from ..errors import AuthError
from ..settings import home

SERVICE = "agentguard"


class TokenStore:
    def __init__(self, backend: str | None = None, path: Path | None = None) -> None:
        self.backend = backend or os.environ.get("AGENTGUARD_TOKEN_STORE") or _default_backend()
        self.path = path or home() / "tokens.enc"
        self._memory: dict[str, str] = {}
        self._lock = threading.Lock()

    def get(self, account: str) -> dict[str, Any] | None:
        raw = self._read(account)
        return None if raw is None else dict(json.loads(raw))

    def set(self, account: str, data: dict[str, Any]) -> None:
        self._write(account, json.dumps(data))

    def delete(self, account: str) -> None:
        self._write(account, None)

    def _read(self, account: str) -> str | None:
        if self.backend == "memory":
            return self._memory.get(account)
        if self.backend == "keyring":
            import keyring

            return keyring.get_password(SERVICE, account)
        return self._file_load().get(account)

    def _write(self, account: str, value: str | None) -> None:
        if self.backend == "memory":
            if value is None:
                self._memory.pop(account, None)
            else:
                self._memory[account] = value
            return
        if self.backend == "keyring":
            import keyring
            import keyring.errors

            if value is None:
                with contextlib.suppress(keyring.errors.PasswordDeleteError):
                    keyring.delete_password(SERVICE, account)
            else:
                keyring.set_password(SERVICE, account, value)
            return
        with self._lock:
            data = self._file_load()
            if value is None:
                data.pop(account, None)
            else:
                data[account] = value
            self._file_save(data)

    def _fernet(self) -> Any:
        key = os.environ.get("AGENTGUARD_TOKEN_KEY")
        if not key:
            raise AuthError(
                "no OS keychain available: set AGENTGUARD_TOKEN_KEY to a Fernet key "
                "(python -c 'from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())') to use an encrypted token file"
            )
        from cryptography.fernet import Fernet

        return Fernet(key.encode())

    def _file_load(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        data = self._fernet().decrypt(self.path.read_bytes())
        return dict(json.loads(data))

    def _file_save(self, data: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        blob = self._fernet().encrypt(json.dumps(data).encode())
        tmp = self.path.with_suffix(".tmp")
        tmp.write_bytes(blob)
        tmp.chmod(0o600)
        tmp.replace(self.path)


def _default_backend() -> str:
    try:
        import keyring
        from keyring.backends import fail

        return "file" if isinstance(keyring.get_keyring(), fail.Keyring) else "keyring"
    except Exception:
        return "file"
