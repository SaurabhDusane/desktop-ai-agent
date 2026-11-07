"""Deterministic multi-application plan runner; UI actions are serialized."""

from desktop_agent.agent.models import AgentPlan, PlanResult, StepResult
from desktop_agent.agent.registry import ToolRegistry


class PlanValidationError(ValueError):
    pass


def validate_plan(plan: AgentPlan) -> None:
    if not plan.goal.strip():
        raise PlanValidationError("Plan goal cannot be empty")
    ids = [step.step_id for step in plan.steps]
    if len(ids) != len(set(ids)):
        raise PlanValidationError("Plan step IDs must be unique")
    known: set[str] = set()
    for step in plan.steps:
        if not step.step_id or not step.description:
            raise PlanValidationError("Every step needs an ID and description")
        missing = set(step.depends_on) - known
        if missing:
            raise PlanValidationError(f"Step {step.step_id} has missing or forward dependencies: {sorted(missing)}")
        known.add(step.step_id)


class PlanRunner:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def run(self, plan: AgentPlan) -> PlanResult:
        validate_plan(plan)
        results: list[StepResult] = []
        completed: set[str] = set()
        for step in plan.steps:
            if not set(step.depends_on).issubset(completed):
                results.append(StepResult(step.step_id, "skipped", message="Dependency did not complete."))
                return PlanResult(plan.goal, "stopped", tuple(results))
            try:
                output = self.registry.execute(step.call)
            except PermissionError as exc:
                results.append(StepResult(step.step_id, "denied", message=str(exc)))
                return PlanResult(plan.goal, "approval_required", tuple(results))
            except Exception as exc:
                results.append(StepResult(step.step_id, "failed", message=str(exc)))
                return PlanResult(plan.goal, "failed", tuple(results))
            results.append(StepResult(step.step_id, "completed", output=output))
            completed.add(step.step_id)
        return PlanResult(plan.goal, "completed", tuple(results))
