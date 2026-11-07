"""Register application adapter operations as centrally governed tools."""
from __future__ import annotations
from typing import Any
from desktop_agent.agent.registry import ToolRegistry, ToolSpec
from desktop_agent.desktop.adapters import AdapterRegistry
from desktop_agent.desktop.windows_adapter import WindowsDesktopAdapter
from desktop_agent.desktop.uia import WindowsUIAutomation

def register_adapter_tools(registry: ToolRegistry, adapters: AdapterRegistry) -> None:
    """Expose declared adapter operations through ToolRegistry policy and audit."""
    for descriptor in adapters.descriptors():
        for operation in adapters.operations(descriptor.adapter_id):
            tool_name = f"{descriptor.adapter_id}_{operation.name}"
            def handler(_adapter_id=descriptor.adapter_id, _operation=operation.name,
                        **arguments: Any) -> Any:
                return adapters.invoke(_adapter_id, _operation, arguments)
            registry.register(ToolSpec(
                name=tool_name, description=f"{descriptor.display_name}: {operation.description}",
                risk=operation.risk, handler=handler, input_schema=operation.input_schema,
                capabilities=operation.capabilities,
            ))

def register_uia_tools(registry: ToolRegistry,
                       automation: WindowsUIAutomation | None = None) -> AdapterRegistry:
    """Compatibility entry point; registers Windows UIA as the first adapter."""
    adapters = AdapterRegistry()
    adapters.register(WindowsDesktopAdapter(automation))
    register_adapter_tools(registry, adapters)
    return adapters
