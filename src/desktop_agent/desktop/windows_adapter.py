"""First application adapter: conservative Windows desktop UI Automation."""
from __future__ import annotations
from typing import Any
from desktop_agent.agent.capabilities import Capability
from desktop_agent.agent.models import RiskLevel
from desktop_agent.desktop.adapters import AdapterDescriptor, AdapterOperation, ApplicationAdapter
from desktop_agent.desktop.uia import WindowsUIAutomation

_OBSERVE = (Capability("desktop", frozenset({"observe"})),)
_INTERACT = (Capability("desktop", frozenset({"interact"})),)

def _object(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required,
            "additionalProperties": False}

class WindowsDesktopAdapter(ApplicationAdapter):
    """Expose only the existing bounded UIA operations through a common contract."""
    def __init__(self, automation: WindowsUIAutomation | None = None) -> None:
        self.automation = automation or WindowsUIAutomation()
        self._descriptor = AdapterDescriptor(
            "windows_desktop", "Windows Desktop", "windows",
            "Visible-window discovery and bounded UI Automation.",
        )
        window = {"title": {"type": "string", "maxLength": 200}}
        pid = {"process_id": {"type": "integer"}}
        self._operations = (
            AdapterOperation("list_windows", "List visible windows without reading their contents.",
                RiskLevel.READ_ONLY, _object({}, []), _OBSERVE),
            AdapterOperation("inspect_controls", "Inspect a bounded control tree without reading field values.",
                RiskLevel.READ_ONLY, _object({**window, **pid,
                    "max_depth": {"type": "integer"}, "max_nodes": {"type": "integer"}}, ["title"]), _OBSERVE),
            AdapterOperation("focus_window", "Focus one exact visible window.",
                RiskLevel.SYSTEM_CHANGE, _object({**window, **pid}, ["title"]), _INTERACT),
            AdapterOperation("click_control", "Click exactly one uniquely matched control.",
                RiskLevel.SENSITIVE, _object({**window, **pid,
                    "control_type": {"type": "string", "maxLength": 60},
                    "automation_id": {"type": "string", "maxLength": 120},
                    "name": {"type": "string", "maxLength": 80}},
                    ["title", "control_type"]), _INTERACT),
            AdapterOperation("type_text", "Enter text into exactly one uniquely matched control.",
                RiskLevel.SENSITIVE, _object({**window, **pid,
                    "control_type": {"type": "string", "maxLength": 60},
                    "automation_id": {"type": "string", "maxLength": 120},
                    "name": {"type": "string", "maxLength": 80},
                    "text": {"type": "string", "maxLength": 10000}},
                    ["title", "control_type", "text"]), _INTERACT),
        )

    @property
    def descriptor(self) -> AdapterDescriptor:
        return self._descriptor

    @property
    def operations(self) -> tuple[AdapterOperation, ...]:
        return self._operations

    def execute(self, operation: str, arguments: dict[str, Any]) -> Any:
        args = dict(arguments)
        process_id = args.pop("process_id", 0) or None
        if operation == "list_windows":
            if args:
                raise ValueError("list_windows accepts no arguments.")
            return self.automation.list_windows()
        if operation == "inspect_controls":
            return self.automation.inspect_controls(args["title"], process_id,
                args.get("max_depth", 2), args.get("max_nodes", 80))
        if operation == "focus_window":
            return self.automation.focus_window(args["title"], process_id)
        if operation == "click_control":
            return self.automation.click_control(args["title"], args["control_type"],
                args.get("automation_id", ""), args.get("name", ""), process_id)
        if operation == "type_text":
            return self.automation.type_text(args["title"], args["control_type"], args["text"],
                args.get("automation_id", ""), args.get("name", ""), process_id)
        raise KeyError(f"Unsupported Windows desktop operation: {operation}")
