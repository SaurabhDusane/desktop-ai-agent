import pytest

from desktop_agent.agent.audit import AuditLog
from desktop_agent.agent.models import RiskLevel, ToolCall
from desktop_agent.agent.policy import PermissionPolicy
from desktop_agent.agent.registry import ToolRegistry, ToolSpec


def test_sensitive_uia_action_requires_per_action_approval(tmp_path):
    policy = PermissionPolicy()
    registry = ToolRegistry(policy, AuditLog(tmp_path / "audit.db"))
    registry.register(ToolSpec("desktop_click_control", "Click", RiskLevel.SENSITIVE, lambda: "clicked"))
    with pytest.raises(PermissionError):
        registry.execute(ToolCall("desktop_click_control"))
    assert registry.audit_log.recent_events()[0]["outcome"] == "denied"


def test_approval_callback_is_per_invocation(tmp_path):
    approvals = []
    registry = ToolRegistry(
        PermissionPolicy(),
        AuditLog(tmp_path / "audit.db"),
        lambda name, reason, args: approvals.append(name) or True,
    )
    registry.register(ToolSpec("desktop_type_text", "Type", RiskLevel.SENSITIVE, lambda text: len(text)))
    assert registry.execute(ToolCall("desktop_type_text", {"text": "hello"})) == 5
    assert approvals == ["desktop_type_text"]


def test_sensitive_actions_ignore_session_grants(tmp_path):
    policy = PermissionPolicy()
    policy.grant_for_session("desktop_click_control")
    registry = ToolRegistry(policy, AuditLog(tmp_path / "audit-grant.db"))
    registry.register(ToolSpec("desktop_click_control", "Click", RiskLevel.SENSITIVE, lambda: "clicked"))
    with pytest.raises(PermissionError):
        registry.execute(ToolCall("desktop_click_control"))
