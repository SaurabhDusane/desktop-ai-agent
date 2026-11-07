"""Live task dashboard for scheduled tool execution."""

from __future__ import annotations

from datetime import datetime
from PySide6.QtWidgets import QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from desktop_agent.agent.scheduler import SchedulerMetrics, TaskEvent


class TaskDashboard(QWidget):
    """Bounded, session-local view of task state and scheduler health."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.summary = QLabel("No tasks submitted this session.")
        self.approval = QLabel("Pending approvals: none")
        self.metrics = QLabel("Scheduler: idle")
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Plan", "Step", "State", "Updated", "Duration", "Details"]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout = QVBoxLayout(self)
        layout.addWidget(self.summary)
        layout.addWidget(self.approval)
        layout.addWidget(self.metrics)
        layout.addWidget(self.table, 1)
        self._rows: dict[tuple[str, str], int] = {}
        self._states: dict[str, int] = {}

    def add_event(self, event: TaskEvent) -> None:
        key = (event.plan_id, event.step_id)
        row = self._rows.get(key)
        if row is None:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self._rows[key] = row
        values = (
            event.plan_id[:12], event.step_id, event.state.value,
            datetime.fromtimestamp(event.timestamp).strftime("%H:%M:%S"),
            f"{event.duration_seconds:.3f}s" if event.duration_seconds is not None else "—",
            event.detail or (self.table.item(row, 5).text() if self.table.item(row, 5) else "—"),
        )
        for column, value in enumerate(values):
            self.table.setItem(row, column, QTableWidgetItem(value))
        self._states[event.state.value] = self._states.get(event.state.value, 0) + 1
        self.summary.setText(
            f"Task events: {sum(self._states.values())} · "
            + " · ".join(f"{name}: {count}" for name, count in sorted(self._states.items()))
        )
        if self.table.rowCount() > 250:
            self.table.removeRow(0)
            self._rows = {
                key: index - 1 for key, index in self._rows.items() if index > 0
            }

    def set_approval(self, tool_name: str, pending: bool) -> None:
        self.approval.setText(
            f"Pending approval: {tool_name}" if pending else "Pending approvals: none"
        )

    def update_metrics(self, metrics: SchedulerMetrics) -> None:
        self.metrics.setText(
            f"Plans submitted: {metrics.submitted_plans} · completed: {metrics.completed_plans} · "
            f"failed: {metrics.failed_plans} · rejected: {metrics.rejected_plans} · "
            f"active plans: {metrics.active_plans} · active steps: {metrics.active_steps} · "
            f"average step: {metrics.average_step_seconds:.3f}s"
        )
