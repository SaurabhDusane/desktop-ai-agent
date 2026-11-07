import pytest

from desktop_agent.agent.audit import AuditLog
from desktop_agent.agent.models import RiskLevel, ToolCall
from desktop_agent.agent.policy import Decision, PermissionPolicy
from desktop_agent.agent.registry import ToolRegistry, ToolSpec


def make_registry(tmp_path, approval=None):
    policy = PermissionPolicy()
    audit = AuditLog(tmp_path / "audit.sqlite3")
    registry = ToolRegistry(policy, audit, approval)
    registry.register(ToolSpec("read_status", "Read status", RiskLevel.READ_ONLY, lambda: "ok"))
    registry.register(ToolSpec("change_setting", "Change a setting", RiskLevel.SYSTEM_CHANGE, lambda value: value))
    registry.register(ToolSpec("dangerous", "Restricted", RiskLevel.RESTRICTED, lambda: "no"))
    return registry, policy, audit


def test_read_only_tool_runs_without_approval(tmp_path):
    registry, _, audit = make_registry(tmp_path)
    assert registry.execute(ToolCall("read_status")) == "ok"
    assert audit.recent_events()[0]["outcome"] == "success"


def test_system_change_requires_approval(tmp_path):
    registry, _, audit = make_registry(tmp_path, lambda *args: False)
    with pytest.raises(PermissionError):
        registry.execute(ToolCall("change_setting", {"value": "x"}))
    assert audit.recent_events()[0]["outcome"] == "denied"


def test_approved_system_change_runs(tmp_path):
    registry, _, _ = make_registry(tmp_path, lambda *args: True)
    assert registry.execute(ToolCall("change_setting", {"value": "x"})) == "x"


def test_restricted_tool_is_never_overridden_by_approval(tmp_path):
    registry, _, audit = make_registry(tmp_path, lambda *args: True)
    with pytest.raises(PermissionError):
        registry.execute(ToolCall("dangerous"))
    assert audit.recent_events()[0]["decision"] == Decision.DENY.value


def test_audit_redacts_sensitive_argument_keys(tmp_path):
    registry, _, audit = make_registry(tmp_path)
    registry.execute(ToolCall("read_status"))
    # Exercise redaction directly through an event payload.
    from desktop_agent.agent.audit import redact
    assert redact({"api_key": "secret-value", "label": "safe"}) == {
        "api_key": "[REDACTED]", "label": "safe"
    }
