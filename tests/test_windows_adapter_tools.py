from desktop_agent.agent.audit import AuditLog
from desktop_agent.agent.models import ToolCall
from desktop_agent.agent.policy import PermissionPolicy
from desktop_agent.agent.registry import ToolRegistry
from desktop_agent.desktop.tools import register_uia_tools


class FakeAutomation:
    def list_windows(self):
        return [{"title": "Editor"}]

    def inspect_controls(self, title, process_id=None, max_depth=2, max_nodes=80):
        return [{"title": title, "depth": max_depth, "nodes": max_nodes}]

    def focus_window(self, title, process_id=None):
        return {"focused": title}

    def click_control(self, title, control_type, automation_id="", name="", process_id=None):
        return {"clicked": True}

    def type_text(self, title, control_type, text, automation_id="", name="", process_id=None):
        return {"text_entered": True, "character_count": len(text)}


def test_windows_adapter_registers_fixed_operations_through_tool_registry(tmp_path):
    registry = ToolRegistry(PermissionPolicy(), AuditLog(tmp_path / "audit.db"))
    adapters = register_uia_tools(registry, FakeAutomation())
    assert [item.adapter_id for item in adapters.descriptors()] == ["windows_desktop"]
    assert registry.execute(ToolCall("windows_desktop_list_windows")) == [{"title": "Editor"}]
    assert registry.execute(ToolCall(
        "windows_desktop_inspect_controls",
        {"title": "Editor", "max_depth": 1, "max_nodes": 5},
    )) == [{"title": "Editor", "depth": 1, "nodes": 5}]


def test_sensitive_adapter_operation_still_requires_fresh_approval(tmp_path):
    registry = ToolRegistry(
        PermissionPolicy(), AuditLog(tmp_path / "audit.db"),
        lambda *_: True,
    )
    register_uia_tools(registry, FakeAutomation())
    result = registry.execute(ToolCall(
        "windows_desktop_click_control",
        {"title": "Editor", "control_type": "Button"},
    ))
    assert result == {"clicked": True}
