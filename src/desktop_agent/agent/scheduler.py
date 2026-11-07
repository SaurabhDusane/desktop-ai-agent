"""Bounded asynchronous plan scheduling with cooperative cancellation and events."""
from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from enum import Enum
import threading
import time
from typing import Any, Callable

from desktop_agent.agent.models import AgentPlan, PlanResult, StepResult, RiskLevel
from desktop_agent.agent.orchestrator import validate_plan
from desktop_agent.agent.registry import ToolRegistry


class TaskState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DENIED = "denied"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class TaskEvent:
    plan_id: str
    step_id: str
    state: TaskState
    timestamp: float
    duration_seconds: float | None = None
    detail: str = ""


@dataclass(frozen=True, slots=True)
class SchedulerMetrics:
    submitted_plans: int
    completed_plans: int
    failed_plans: int
    rejected_plans: int
    active_plans: int
    active_steps: int
    average_step_seconds: float


@dataclass
class PlanHandle:
    plan_id: str
    future: Future[PlanResult]
    _cancel_event: threading.Event = field(repr=False)

    def cancel(self) -> bool:
        """Request cooperative cancellation; an already-running handler may finish."""
        if self.future.done():
            return False
        self._cancel_event.set()
        return True

    @property
    def cancelled(self) -> bool:
        return self._cancel_event.is_set()


class SchedulerFullError(RuntimeError):
    pass


class TaskScheduler:
    """Runs dependency-ready read-only steps concurrently; serializes mutations.

    A plan coordinator owns dependency scheduling. Tool handlers always execute
    through ToolRegistry, so capability, risk, approval, and audit checks remain
    authoritative. Cancellation/deadlines are cooperative at step boundaries;
    Python cannot safely kill a handler already executing in another thread.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        max_workers: int = 3,
        max_queued_plans: int = 4,
        event_callback: Callable[[TaskEvent], None] | None = None,
    ) -> None:
        if max_workers < 1 or max_queued_plans < 1:
            raise ValueError("Worker and queue limits must be positive.")
        self.registry = registry
        self.max_workers = max_workers
        self.max_queued_plans = max_queued_plans
        self.event_callback = event_callback
        self._tool_pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="agent-step")
        self._plan_slots = threading.BoundedSemaphore(max_queued_plans)
        self._mutation_lock = threading.Lock()
        self._lock = threading.RLock()
        self._closed = False
        self._submitted = self._completed = self._failed = self._rejected = 0
        self._active_plans = self._active_steps = 0
        self._durations: list[float] = []

    def submit(self, plan: AgentPlan, plan_id: str, deadline_seconds: float = 120.0) -> PlanHandle:
        validate_plan(plan)
        if not plan_id.strip() or deadline_seconds <= 0:
            raise ValueError("A plan ID and positive deadline are required.")
        with self._lock:
            if self._closed:
                raise RuntimeError("Scheduler is shut down.")
            if not self._plan_slots.acquire(blocking=False):
                self._rejected += 1
                raise SchedulerFullError("Task queue is full; wait for an active plan to finish.")
            self._submitted += 1
            self._active_plans += 1
        cancel_event = threading.Event()
        result_future: Future[PlanResult] = Future()
        thread = threading.Thread(
            target=self._coordinate,
            args=(plan, plan_id, deadline_seconds, cancel_event, result_future),
            name=f"agent-plan-{plan_id[:24]}",
            daemon=True,
        )
        thread.start()
        return PlanHandle(plan_id, result_future, cancel_event)

    def _emit(self, plan_id: str, step_id: str, state: TaskState,
              started: float | None = None, detail: str = "") -> None:
        duration = time.monotonic() - started if started is not None else None
        event = TaskEvent(plan_id, step_id, state, time.time(), duration, detail[:500])
        if duration is not None:
            with self._lock:
                self._durations.append(duration)
                self._durations = self._durations[-500:]
        if self.event_callback:
            try:
                self.event_callback(event)
            except Exception:
                pass

    def _invoke(self, step, plan_id: str, cancel: threading.Event,
                deadline: float) -> tuple[Any, float]:
        if cancel.is_set():
            raise InterruptedError("Cancellation requested before tool execution.")
        if time.monotonic() >= deadline:
            raise TimeoutError("Plan deadline exceeded before tool execution.")
        started = time.monotonic()
        with self._lock:
            self._active_steps += 1
        try:
            risk = self.registry.risk_for(step.call.tool_name)
            if risk is RiskLevel.READ_ONLY:
                value = self.registry.execute(step.call)
            else:
                with self._mutation_lock:
                    if cancel.is_set():
                        raise InterruptedError("Cancellation requested before state-changing action.")
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Plan deadline exceeded before state-changing action.")
                    value = self.registry.execute(step.call)
            return value, time.monotonic() - started
        finally:
            with self._lock:
                self._active_steps -= 1

    def _coordinate(self, plan: AgentPlan, plan_id: str, deadline_seconds: float,
                    cancel: threading.Event, output: Future[PlanResult]) -> None:
        deadline = time.monotonic() + deadline_seconds
        steps = {step.step_id: step for step in plan.steps}
        pending = set(steps)
        running: dict[Future, str] = {}
        results: dict[str, StepResult] = {}
        completed: set[str] = set()
        failed_status = "completed"
        try:
            for step in plan.steps:
                self._emit(plan_id, step.step_id, TaskState.QUEUED)
            while pending or running:
                if cancel.is_set():
                    failed_status = "cancelled"
                    break
                if time.monotonic() >= deadline:
                    failed_status = "timed_out"
                    break

                ready = [sid for sid in pending if set(steps[sid].depends_on).issubset(completed)]
                while ready and len(running) < self.max_workers:
                    sid = ready.pop(0)
                    pending.remove(sid)
                    step = steps[sid]
                    self._emit(plan_id, sid, TaskState.RUNNING)
                    future = self._tool_pool.submit(self._invoke, step, plan_id, cancel, deadline)
                    running[future] = sid

                if not running:
                    if pending:
                        failed_status = "stopped"
                    break

                done, _ = wait(tuple(running), timeout=min(0.1, max(0.0, deadline-time.monotonic())),
                               return_when=FIRST_COMPLETED)
                for future in done:
                    sid = running.pop(future)
                    try:
                        value, duration = future.result()
                        results[sid] = StepResult(sid, "completed", output=value)
                        completed.add(sid)
                        self._emit(plan_id, sid, TaskState.COMPLETED, time.monotonic()-duration)
                    except PermissionError as exc:
                        results[sid] = StepResult(sid, "denied", message=str(exc))
                        self._emit(plan_id, sid, TaskState.DENIED, detail=str(exc))
                        failed_status = "approval_required"
                    except InterruptedError as exc:
                        results[sid] = StepResult(sid, "cancelled", message=str(exc))
                        self._emit(plan_id, sid, TaskState.CANCELLED, detail=str(exc))
                        failed_status = "cancelled"
                    except TimeoutError as exc:
                        results[sid] = StepResult(sid, "timed_out", message=str(exc))
                        self._emit(plan_id, sid, TaskState.TIMED_OUT, detail=str(exc))
                        failed_status = "timed_out"
                    except Exception as exc:
                        results[sid] = StepResult(sid, "failed", message=str(exc))
                        self._emit(plan_id, sid, TaskState.FAILED, detail=str(exc))
                        failed_status = "failed"
                if failed_status != "completed":
                    break

            if failed_status != "completed":
                cancel.set()
                for future, sid in list(running.items()):
                    future.cancel()
                    if future.cancelled():
                        results[sid] = StepResult(sid, "cancelled", message="Cancelled before start.")
                        self._emit(plan_id, sid, TaskState.CANCELLED)
                for sid in pending:
                    results[sid] = StepResult(sid, "skipped", message="Plan stopped before this step.")
                    self._emit(plan_id, sid, TaskState.SKIPPED)
                # Do not report success while a running handler is still executing.
                for future, sid in list(running.items()):
                    if future.cancelled():
                        continue
                    try:
                        value, _ = future.result(timeout=max(0.0, deadline-time.monotonic()))
                        results[sid] = StepResult(sid, "completed", output=value)
                        self._emit(plan_id, sid, TaskState.COMPLETED)
                    except Exception as exc:
                        results[sid] = StepResult(sid, "failed", message=str(exc))
                        self._emit(plan_id, sid, TaskState.FAILED, detail="Handler ended after cancellation/deadline.")
            ordered = tuple(results[s.step_id] for s in plan.steps if s.step_id in results)
            result = PlanResult(plan.goal, failed_status, ordered)
            output.set_result(result)
            with self._lock:
                if failed_status == "completed":
                    self._completed += 1
                else:
                    self._failed += 1
        except Exception as exc:
            output.set_exception(exc)
            with self._lock:
                self._failed += 1
        finally:
            with self._lock:
                self._active_plans -= 1
            self._plan_slots.release()

    def metrics(self) -> SchedulerMetrics:
        with self._lock:
            average = sum(self._durations) / len(self._durations) if self._durations else 0.0
            return SchedulerMetrics(
                self._submitted, self._completed, self._failed, self._rejected,
                self._active_plans, self._active_steps, average,
            )

    def shutdown(self, wait_for_tasks: bool = True) -> None:
        with self._lock:
            self._closed = True
        self._tool_pool.shutdown(wait=wait_for_tasks, cancel_futures=not wait_for_tasks)
