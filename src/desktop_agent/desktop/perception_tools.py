"""Register explicit screen perception through the central tool policy."""
from desktop_agent.agent.capabilities import Capability
from desktop_agent.agent.models import RiskLevel
from desktop_agent.agent.registry import ToolRegistry, ToolSpec
from desktop_agent.desktop.perception import PerceptionBroker


def register_perception_tools(registry: ToolRegistry, broker: PerceptionBroker) -> None:
    """Expose a single bounded primary-display observation operation."""
    registry.register(ToolSpec(
        name="perception_describe_primary_screen",
        description=(
            "With fresh user approval, capture the primary display once and describe "
            "its visible contents using an installed local vision model. The screenshot "
            "is held in memory only and is not saved."
        ),
        risk=RiskLevel.SENSITIVE,
        handler=broker.describe_primary_screen,
        input_schema={
            "type": "object", "properties": {}, "required": [],
            "additionalProperties": False,
        },
        capabilities=(Capability("desktop", frozenset({"capture"}), "primary_display"),),
    ))
