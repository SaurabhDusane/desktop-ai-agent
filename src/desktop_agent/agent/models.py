"""Typed task-plan models shared by the planner and executor."""

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class RiskLevel(IntEnum):
    READ_ONLY = 0
    ROUTINE = 1
    SYSTEM_CHANGE = 2
    SENSITIVE = 3
    RESTRICTED = 4


@dataclass(frozen=True, slots=True)
class ToolCall:
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    application: str | None = None


@dataclass(frozen=True, slots=True)
class PlanStep:
    step_id: str
    description: str
    call: ToolCall
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AgentPlan:
    goal: str
    steps: tuple[PlanStep, ...]


@dataclass(frozen=True, slots=True)
class StepResult:
    step_id: str
    status: str
    output: Any = None
    message: str = ""


@dataclass(frozen=True, slots=True)
class PlanResult:
    goal: str
    status: str
    steps: tuple[StepResult, ...]
