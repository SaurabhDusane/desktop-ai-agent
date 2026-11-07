import threading
import time

import pytest

from desktop_agent.agent.audit import AuditLog
from desktop_agent.agent.models import AgentPlan, PlanStep, RiskLevel, ToolCall
from desktop_agent.agent.policy import PermissionPolicy
from desktop_agent.agent.registry import ToolRegistry, ToolSpec
from desktop_agent.agent.scheduler import SchedulerFullError, TaskScheduler, TaskState


def make_registry(tmp_path):
    return ToolRegistry(PermissionPolicy(), AuditLog(tmp_path / "audit.sqlite3"))


def test_independent_read_only_steps_run_concurrently_and_emit_events(tmp_path):
    registry = make_registry(tmp_path)
    barrier = threading.Barrier(2, timeout=2)
    registry.register(ToolSpec("read_a", "A", RiskLevel.READ_ONLY, lambda: barrier.wait() or "a"))
    registry.register(ToolSpec("read_b", "B", RiskLevel.READ_ONLY, lambda: barrier.wait() or "b"))
    events = []
    scheduler = TaskScheduler(registry, max_workers=2, event_callback=events.append)
    plan = AgentPlan("parallel reads", (
        PlanStep("a", "read A", ToolCall("read_a")),
        PlanStep("b", "read B", ToolCall("read_b")),
    ))
    try:
        result = scheduler.submit(plan, "parallel").future.result(timeout=5)
        assert result.status == "completed"
        assert {step.status for step in result.steps} == {"completed"}
        assert {event.state for event in events} >= {TaskState.QUEUED, TaskState.RUNNING, TaskState.COMPLETED}
        assert scheduler.metrics().completed_plans == 1
    finally:
        scheduler.shutdown()


def test_dependency_failure_skips_downstream_steps(tmp_path):
    registry = make_registry(tmp_path)
    seen = []
    def fail():
        raise RuntimeError("failed safely")
    registry.register(ToolSpec("fail", "fail", RiskLevel.READ_ONLY, fail))
    registry.register(ToolSpec("next", "next", RiskLevel.READ_ONLY, lambda: seen.append(True)))
    plan = AgentPlan("dependent", (
        PlanStep("one", "fail", ToolCall("fail")),
        PlanStep("two", "next", ToolCall("next"), ("one",)),
    ))
    scheduler = TaskScheduler(registry)
    try:
        result = scheduler.submit(plan, "failure").future.result(timeout=5)
        assert result.status == "failed"
        assert [step.status for step in result.steps] == ["failed", "skipped"]
        assert not seen
    finally:
        scheduler.shutdown()


def test_state_changing_steps_are_serialized(tmp_path):
    registry = make_registry(tmp_path)
    lock = threading.Lock()
    active = 0
    maximum = 0
    def change():
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.05)
        with lock:
            active -= 1
    registry.register(ToolSpec("change_a", "A", RiskLevel.SYSTEM_CHANGE, change))
    registry.register(ToolSpec("change_b", "B", RiskLevel.SENSITIVE, change))
    plan = AgentPlan("mutations", (
        PlanStep("a", "change A", ToolCall("change_a")),
        PlanStep("b", "change B", ToolCall("change_b")),
    ))
    scheduler = TaskScheduler(registry, max_workers=2)
    try:
        result = scheduler.submit(plan, "mutations").future.result(timeout=5)
        assert result.status == "approval_required"  # sensitive/system changes require approval
        assert maximum <= 1
    finally:
        scheduler.shutdown()


def test_queue_is_bounded(tmp_path):
    registry = make_registry(tmp_path)
    gate = threading.Event()
    registry.register(ToolSpec("wait", "wait", RiskLevel.READ_ONLY, lambda: gate.wait(2)))
    plan = AgentPlan("blocked", (PlanStep("a", "wait", ToolCall("wait")),))
    scheduler = TaskScheduler(registry, max_queued_plans=1)
    try:
        first = scheduler.submit(plan, "one")
        time.sleep(0.05)
        with pytest.raises(SchedulerFullError):
            scheduler.submit(plan, "two")
        gate.set()
        assert first.future.result(timeout=5).status == "completed"
        assert scheduler.metrics().rejected_plans == 1
    finally:
        gate.set()
        scheduler.shutdown()


def test_cancellation_before_start_marks_pending_steps(tmp_path):
    registry = make_registry(tmp_path)
    gate = threading.Event()
    started = threading.Event()
    def slow():
        started.set()
        gate.wait(2)
        return "finished"
    registry.register(ToolSpec("slow", "slow", RiskLevel.READ_ONLY, slow))
    registry.register(ToolSpec("later", "later", RiskLevel.READ_ONLY, lambda: "later"))
    plan = AgentPlan("cancel", (
        PlanStep("one", "slow", ToolCall("slow")),
        PlanStep("two", "later", ToolCall("later"), ("one",)),
    ))
    scheduler = TaskScheduler(registry)
    try:
        handle = scheduler.submit(plan, "cancel")
        assert started.wait(2)
        assert handle.cancel()
        gate.set()
        result = handle.future.result(timeout=5)
        assert result.status == "cancelled"
        assert result.steps[0].status == "completed"  # already-running handler was not killed
        assert result.steps[1].status == "skipped"
    finally:
        gate.set()
        scheduler.shutdown()


def test_deadline_rejects_steps_not_yet_started(tmp_path):
    registry = make_registry(tmp_path)
    seen = []
    registry.register(ToolSpec("noop", "noop", RiskLevel.READ_ONLY, lambda: seen.append(True)))
    plan = AgentPlan("expired", (PlanStep("a", "noop", ToolCall("noop")),))
    scheduler = TaskScheduler(registry)
    try:
        handle = scheduler.submit(plan, "deadline", deadline_seconds=0.000001)
        result = handle.future.result(timeout=5)
        assert result.status == "timed_out"
        assert not seen
    finally:
        scheduler.shutdown()
