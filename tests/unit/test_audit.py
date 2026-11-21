from __future__ import annotations

from pathlib import Path

from agentguard.audit import AuditLog, fingerprint_all, redact


def test_assignments_in_free_text_are_redacted() -> None:
    out = redact({"body": "Config: DEPLOY_KEY=fake-3f9a and db_password: hunter2, ok"})
    assert "fake-3f9a" not in out["body"] and "hunter2" not in out["body"]
    assert out["body"].startswith("Config: DEPLOY_KEY=<redacted sha256:")
    assert out["body"].endswith(", ok")


def test_ordinary_text_is_kept() -> None:
    assert redact({"body": "The keyboard works; see key points."}) == {
        "body": "The keyboard works; see key points."
    }


def test_leak_payloads_are_fingerprinted() -> None:
    out = fingerprint_all(
        {"repo": "demo-public", "files": [{"path": "a", "content": "x=1"}], "n": 3}
    )
    assert out["n"] == 3 and out["repo"].startswith("<11 chars sha256:")
    assert "x=1" not in str(out)


def test_audit_file_is_private(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "audit.jsonl")
    log.write({"a": 1})
    assert oct((tmp_path / "audit.jsonl").stat().st_mode & 0o777) == "0o600"
