"""Expose environment graph refresh and query through the central tool registry."""
from __future__ import annotations

from desktop_agent.agent.models import RiskLevel
from desktop_agent.agent.registry import ToolRegistry, ToolSpec
from desktop_agent.desktop.environment import EnvironmentStateService


def register_environment_tools(
    registry: ToolRegistry,
    service: EnvironmentStateService,
) -> None:
    registry.register(ToolSpec(
        name="environment_refresh_desktop",
        description=(
            "Refresh the local environment graph from visible window metadata. "
            "This performs an on-demand read; it does not capture screenshots or document contents."
        ),
        risk=RiskLevel.READ_ONLY,
        handler=service.refresh_desktop,
        input_schema={
            "type": "object", "properties": {}, "required": [],
            "additionalProperties": False,
        },
    ))
    registry.register(ToolSpec(
        name="environment_snapshot",
        description="Return a bounded snapshot of the current session's environment graph.",
        risk=RiskLevel.READ_ONLY,
        handler=service.graph.snapshot,
        input_schema={
            "type": "object",
            "properties": {
                "kind": {"type": "string", "maxLength": 40},
                "limit": {"type": "integer"},
            },
            "required": [],
            "additionalProperties": False,
        },
    ))
    registry.register(ToolSpec(
        name="environment_query",
        description="Find nodes in the current session's environment graph by metadata text and optional kind.",
        risk=RiskLevel.READ_ONLY,
        handler=service.graph.query,
        input_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string", "maxLength": 200},
                "kind": {"type": "string", "maxLength": 40},
                "limit": {"type": "integer"},
            },
            "required": [],
            "additionalProperties": False,
        },
    ))
