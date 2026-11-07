"""Register Windows UIA capabilities through the central permission/audit layer."""
from desktop_agent.agent.models import RiskLevel
from desktop_agent.agent.registry import ToolRegistry, ToolSpec
from desktop_agent.desktop.uia import WindowsUIAutomation


def register_uia_tools(registry: ToolRegistry, automation: WindowsUIAutomation | None = None) -> None:
    uia = automation or WindowsUIAutomation()
    registry.register(ToolSpec(
        "desktop_list_windows", "List visible top-level windows without reading their contents.",
        RiskLevel.READ_ONLY, uia.list_windows,
    ))
    registry.register(ToolSpec(
        "desktop_inspect_controls", "Inspect a bounded UI Automation control tree without reading edit values.",
        RiskLevel.READ_ONLY, uia.inspect_controls,
    ))
    registry.register(ToolSpec(
        "desktop_focus_window", "Focus one exact visible window; requires explicit approval.",
        RiskLevel.SYSTEM_CHANGE, uia.focus_window,
    ))
    registry.register(ToolSpec(
        "desktop_click_control", "Click one uniquely matched UI control; requires per-action approval.",
        RiskLevel.SENSITIVE, uia.click_control,
    ))
    registry.register(ToolSpec(
        "desktop_type_text", "Enter text into one uniquely matched control; requires per-action approval.",
        RiskLevel.SENSITIVE, uia.type_text,
    ))
