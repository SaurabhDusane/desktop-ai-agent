import pytest

from desktop_agent.agent.audit import AuditLog
from desktop_agent.agent.models import RiskLevel, ToolCall
from desktop_agent.agent.policy import PermissionPolicy
from desktop_agent.agent.registry import ToolRegistry, ToolSpec


def test_unknown_arguments_are_rejected_before_handler(tmp_path):
    seen = []
    registry = ToolRegistry(PermissionPolicy(), AuditLog(tmp_path / "audit.db"))
    registry.register(ToolSpec(
        "set_value", "Set a value", RiskLevel.READ_ONLY, lambda value: seen.append(value),
        {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"], "additionalProperties": False},
    ))
    with pytest.raises(ValueError, match="unknown"):
        registry.execute(ToolCall("set_value", {"value": "safe", "command": "whoami"}))
    assert seen == []


def test_argument_type_is_checked(tmp_path):
    registry = ToolRegistry(PermissionPolicy(), AuditLog(tmp_path / "audit.db"))
    registry.register(ToolSpec(
        "set_value", "Set a value", RiskLevel.READ_ONLY, lambda value: value,
        {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"], "additionalProperties": False},
    ))
    with pytest.raises(ValueError, match="must be string"):
        registry.execute(ToolCall("set_value", {"value": 42}))
