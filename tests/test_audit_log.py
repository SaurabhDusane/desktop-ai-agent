import json

import pytest

from desktop_agent.agent.audit import AuditLog, redact


def test_jsonl_records_are_valid_lines_and_hash_chain_verifies(tmp_path):
    audit = AuditLog(tmp_path / "audit.sqlite3")
    audit.record_event("chat_message", {"content": "hello"})
    audit.record_event("tool_result", {"password": "dont-log"})
    lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert all(isinstance(json.loads(line)["hash"], str) for line in lines)
    assert audit.verify_jsonl()


def test_reopening_audit_log_continues_chain(tmp_path):
    path = tmp_path / "audit.sqlite3"
    AuditLog(path).record_event("first")
    reopened = AuditLog(path)
    reopened.record_event("second")
    assert reopened.verify_jsonl()


def test_tampered_jsonl_fails_closed(tmp_path):
    path = tmp_path / "audit.sqlite3"
    audit = AuditLog(path)
    audit.record_event("first")
    log = tmp_path / "audit.jsonl"
    log.write_text(log.read_text(encoding="utf-8").replace("first", "edited"), encoding="utf-8")
    with pytest.raises(RuntimeError):
        AuditLog(path)


def test_string_secret_redaction():
    assert redact({"message": "token=abc123"})["message"] == "token=[REDACTED]"
