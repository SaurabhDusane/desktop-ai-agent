from desktop_agent.agent.audit import AuditLog
from desktop_agent.agent.models import AgentPlan, PlanStep, RiskLevel, ToolCall
from desktop_agent.agent.orchestrator import PlanRunner, validate_plan, PlanValidationError
from desktop_agent.agent.policy import PermissionPolicy
from desktop_agent.agent.registry import ToolRegistry, ToolSpec


def test_plan_runs_steps_in_dependency_order(tmp_path):
    registry = ToolRegistry(PermissionPolicy(), AuditLog(tmp_path / "audit.db"))
    seen = []
    registry.register(ToolSpec("first", "first", RiskLevel.READ_ONLY, lambda: seen.append("first")))
    registry.register(ToolSpec("second", "second", RiskLevel.READ_ONLY, lambda: seen.append("second")))
    plan = AgentPlan("coordinate apps", (
        PlanStep("one", "Inspect app A", ToolCall("first", application="app-a")),
        PlanStep("two", "Inspect app B", ToolCall("second", application="app-b"), ("one",)),
    ))
    result = PlanRunner(registry).run(plan)
    assert result.status == "completed"
    assert seen == ["first", "second"]


def test_plan_rejects_forward_dependencies():
    plan = AgentPlan("invalid", (
        PlanStep("one", "first", ToolCall("noop"), ("two",)),
        PlanStep("two", "second", ToolCall("noop")),
    ))
    try:
        validate_plan(plan)
    except PlanValidationError:
        pass
    else:
        raise AssertionError("Expected plan validation failure")
