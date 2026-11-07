"""Application adapter contract and allowlisted adapter registry.
Adapters declare fixed operations; they never receive model-generated code or commands.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Protocol
from desktop_agent.agent.capabilities import Capability
from desktop_agent.agent.models import RiskLevel

@dataclass(frozen=True, slots=True)
class AdapterDescriptor:
    adapter_id: str
    display_name: str
    platform: str
    description: str

@dataclass(frozen=True, slots=True)
class AdapterOperation:
    name: str
    description: str
    risk: RiskLevel
    input_schema: dict[str, Any]
    capabilities: tuple[Capability, ...] = ()

class ApplicationAdapter(Protocol):
    @property
    def descriptor(self) -> AdapterDescriptor: ...
    @property
    def operations(self) -> tuple[AdapterOperation, ...]: ...
    def execute(self, operation: str, arguments: dict[str, Any]) -> Any: ...

class AdapterRegistry:
    """Stores trusted adapters and dispatches only declared operation names."""
    def __init__(self) -> None:
        self._adapters: dict[str, ApplicationAdapter] = {}

    def register(self, adapter: ApplicationAdapter) -> None:
        descriptor = adapter.descriptor
        if not descriptor.adapter_id or descriptor.adapter_id in self._adapters:
            raise ValueError(f"Invalid or duplicate adapter ID: {descriptor.adapter_id!r}")
        operations = adapter.operations
        names = [item.name for item in operations]
        if not names or any(not name for name in names) or len(names) != len(set(names)):
            raise ValueError("An adapter must declare unique, non-empty operation names.")
        for operation in operations:
            schema = operation.input_schema
            if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
                raise ValueError(f"Operation {operation.name!r} must use a closed object schema.")
        self._adapters[descriptor.adapter_id] = adapter

    def get(self, adapter_id: str) -> ApplicationAdapter:
        try:
            return self._adapters[adapter_id]
        except KeyError as exc:
            raise KeyError(f"Unknown application adapter: {adapter_id}") from exc

    def descriptors(self) -> tuple[AdapterDescriptor, ...]:
        return tuple(adapter.descriptor for adapter in self._adapters.values())

    def operations(self, adapter_id: str) -> tuple[AdapterOperation, ...]:
        return self.get(adapter_id).operations

    def invoke(self, adapter_id: str, operation_name: str, arguments: dict[str, Any]) -> Any:
        adapter = self.get(adapter_id)
        operation = next((item for item in adapter.operations if item.name == operation_name), None)
        if operation is None:
            raise KeyError(f"Adapter {adapter_id!r} does not declare operation {operation_name!r}.")
        if not isinstance(arguments, dict):
            raise ValueError("Adapter operation arguments must be an object.")
        schema = operation.input_schema
        properties = schema.get("properties", {})
        unknown = set(arguments) - set(properties)
        missing = set(schema.get("required", [])) - set(arguments)
        if unknown or missing:
            raise ValueError(
                f"Invalid arguments for {adapter_id}.{operation_name}; "
                f"unknown={sorted(unknown)}, missing={sorted(missing)}"
            )
        return adapter.execute(operation_name, arguments)
