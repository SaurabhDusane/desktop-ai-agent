"""Main PySide6 chat window. Ollama requests run off the UI thread."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPushButton, QTextBrowser, QVBoxLayout, QWidget,
)

from desktop_agent.config import Settings
from desktop_agent.ollama import OllamaClient
from desktop_agent.agent.audit import AuditLog
from desktop_agent.agent.memory import RepetitionMemory, SessionContext
from desktop_agent.agent.policy import PermissionPolicy
from desktop_agent.agent.registry import ToolRegistry
from desktop_agent.agent.runtime import AgentRuntime
from desktop_agent.agent.scheduler import TaskScheduler
from desktop_agent.agent.model_router import ModelRouter, profile_from_ollama
from desktop_agent.agent.resources import ResourceMonitor, ResourceBudgetManager
from desktop_agent.agent.models import ToolCall
from desktop_agent.agent.tools import register_desktop_tools
from desktop_agent.ui.approval import ApprovalBroker
from desktop_agent.desktop.environment import EnvironmentStateGraph, EnvironmentStateService
from desktop_agent.desktop.environment_tools import register_environment_tools


class Worker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, operation) -> None:
        super().__init__()
        self.operation = operation

    def run(self) -> None:
        try:
            self.finished.emit(self.operation())
        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.client = OllamaClient(settings.ollama_base_url, settings.ollama_timeout_seconds)
        self.approval_broker = ApprovalBroker(self)
        audit_path = Path.home() / ".local-desktop-agent" / "audit.sqlite3"
        self.audit_log = AuditLog(audit_path)
        self.session_context = SessionContext()
        self.repetition_memory = RepetitionMemory(audit_path.parent / "memory.sqlite3")
        self.permission_policy = PermissionPolicy()
        self.tool_registry = ToolRegistry(
            self.permission_policy, self.audit_log, self.approval_broker.approve
        )
        register_desktop_tools(self.tool_registry)
        self.agent_runtime = AgentRuntime(self.client, self.tool_registry)
        self.model_router = ModelRouter()
        self.resource_monitor = ResourceMonitor()
        self.resource_budgets = ResourceBudgetManager()
        self.installed_models: list[str] = []
        self.task_scheduler = TaskScheduler(
            self.tool_registry,
            max_workers=3,
            max_queued_plans=4,
            event_callback=lambda event: self.audit_log.record_event("task_state", {
                "plan_id": event.plan_id, "step_id": event.step_id,
                "state": event.state.value, "timestamp": event.timestamp,
                "duration_seconds": event.duration_seconds, "detail": event.detail,
            }),
        )
        self.audit_log.record_event("application_started", {"platform": sys.platform})
        self.environment_graph = EnvironmentStateGraph()
        self.desktop_tools_available = False
        self.desktop_tools_error: str | None = None
        window_observer = None
        if sys.platform == "win32":
            try:
                from desktop_agent.desktop.tools import register_uia_tools
                register_uia_tools(self.tool_registry)
                window_observer = lambda: self.tool_registry.execute(
                    ToolCall("windows_desktop_list_windows")
                )
                self.desktop_tools_available = True
                self.audit_log.record_event("desktop_tools_registered")
            except Exception as exc:
                self.desktop_tools_error = str(exc)
                self.audit_log.record_event("desktop_tools_unavailable", {"error": str(exc)})
        self.environment_service = EnvironmentStateService(self.environment_graph, window_observer)
        register_environment_tools(self.tool_registry, self.environment_service)
        self._threads: list[QThread] = []
        self.setWindowTitle("Local Desktop AI Agent")
        self.resize(1000, 700)

        self.model_box = QComboBox()
        self.refresh_button = QPushButton("Refresh models")
        self.read_only_button = QPushButton("Enable read-only")
        self.emergency_button = QPushButton("EMERGENCY STOP")
        self.emergency_button.setStyleSheet("background-color: #9b1c1c; color: white; font-weight: bold;")
        status_text = "Connecting to local Ollama…"
        if self.desktop_tools_available:
            status_text += " Windows desktop tools are registered."
        elif self.desktop_tools_error:
            status_text += f" Desktop automation unavailable: {self.desktop_tools_error}"
        self.status = QLabel(status_text)
        self.chat_view = QTextBrowser()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Message your local model…")
        self.send_button = QPushButton("Send")

        header = QHBoxLayout()
        header.addWidget(QLabel("Model:"))
        header.addWidget(self.model_box, 1)
        header.addWidget(self.refresh_button)
        safety = QHBoxLayout()
        safety.addWidget(self.read_only_button)
        safety.addWidget(self.emergency_button)
        composer = QHBoxLayout()
        composer.addWidget(self.input, 1)
        composer.addWidget(self.send_button)
        layout = QVBoxLayout()
        layout.addLayout(header)
        layout.addWidget(self.status)
        layout.addLayout(safety)
        layout.addWidget(self.chat_view, 1)
        layout.addLayout(composer)
        root = QWidget()
        root.setLayout(layout)
        self.setCentralWidget(root)

        self.refresh_button.clicked.connect(self.refresh_models)
        self.read_only_button.clicked.connect(self._toggle_read_only)
        self.emergency_button.clicked.connect(self._emergency_stop)
        self.send_button.clicked.connect(self.send_message)
        self.input.returnPressed.connect(self.send_message)
        self.refresh_models()

    def _toggle_read_only(self) -> None:
        enabled = not self.permission_policy.read_only
        self.permission_policy.set_read_only(enabled)
        self.audit_log.record_event("read_only_mode_changed", {"enabled": enabled})
        self.read_only_button.setText("Disable read-only" if enabled else "Enable read-only")
        self.status.setText("Read-only mode is active." if enabled else "Read-only mode disabled.")

    def _emergency_stop(self) -> None:
        self.permission_policy.activate_emergency_stop()
        self.tool_registry.revoke_all_capabilities()
        self.audit_log.record_event("emergency_stop_activated")
        self.emergency_button.setEnabled(False)
        self.read_only_button.setEnabled(False)
        self.send_button.setEnabled(False)
        self.input.setEnabled(False)
        self.status.setText("EMERGENCY STOP ACTIVE — tool execution is disabled for this session.")
        QMessageBox.information(
            self, "Emergency stop",
            "All future tool executions are blocked for this session. Restart the application to reset it.",
        )

    def _background(self, operation, success) -> None:
        thread = QThread(self)
        worker = Worker(operation)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(success)
        worker.failed.connect(self._show_error)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._threads.remove(thread) if thread in self._threads else None)
        self._threads.append(thread)
        thread.start()

    def refresh_models(self) -> None:
        self.status.setText("Checking local Ollama models…")
        self.refresh_button.setEnabled(False)

        def load_catalog():
            models = self.client.list_models()
            running = self.client.running_models()
            profiles = []
            for name in models:
                try:
                    profiles.append(profile_from_ollama(name, self.client.model_details(name), running))
                except Exception:
                    # Keep the installed model selectable even when metadata is unavailable.
                    from desktop_agent.agent.model_router import ModelProfile
                    profiles.append(ModelProfile(name))
            return models, profiles, self.resource_monitor.snapshot()

        def loaded(catalog) -> None:
            models, profiles, snapshot = catalog
            self.installed_models = models
            self.model_router.update_profiles(profiles)
            self.model_box.clear()
            self.model_box.addItem("Auto (local routing)")
            self.model_box.addItems(models)
            budget = self.resource_budgets.budget(snapshot)
            selected = self.model_box.currentText()
            self.audit_log.record_event("model_list_refreshed", {
                "count": len(models), "selected_model": selected,
                "available_ram_bytes": snapshot.available_ram_bytes,
                "free_vram_bytes": snapshot.free_vram_bytes,
                "gpu_source": snapshot.gpu_source,
            })
            if models:
                decision = self.model_router.choose(models, available_vram_bytes=snapshot.free_vram_bytes)
                hardware = snapshot.gpu_name or "GPU details unavailable"
                self.status.setText(
                    f"{len(models)} local model(s). Recommended: {decision.model} — {decision.reason}. "
                    f"{hardware}. Context budget: {budget.max_context_tokens} tokens."
                )
            else:
                self.status.setText("Ollama is running, but no models are installed. Pull a model with Ollama.")
            self.refresh_button.setEnabled(True)

        self._background(load_catalog, loaded)

    def send_message(self) -> None:
        prompt = self.input.text().strip()
        model = self.model_box.currentText()
        if model == "Auto (local routing)":
            if not self.installed_models:
                self._show_error("No local models are installed. Refresh the model list first.")
                return
            snapshot = self.resource_monitor.snapshot()
            budget = self.resource_budgets.budget(snapshot)
            decision = self.model_router.choose(
                self.installed_models, task="tools" if self.tool_registry.model_schemas() else "general",
                available_vram_bytes=snapshot.free_vram_bytes,
            )
            model = decision.model
            self.audit_log.record_event("model_routed", {
                "model": model, "reason": decision.reason, "score": decision.score,
                "measured": decision.measured, "context_budget": budget.max_context_tokens,
                "warnings": list(budget.warnings),
            })
            self.status.setText(f"Auto selected {model}. {decision.reason}")
        if not prompt:
            return
        if not model:
            self._show_error("No model selected. Install a model in Ollama, then refresh.")
            return
        self.audit_log.record_event("user_message", {"model": model, "character_count": len(prompt)})
        self.session_context.add("user", prompt)
        self.input.clear()
        self.send_button.setEnabled(False)
        self.chat_view.append(f"<b>You:</b> {self._escape(prompt)}")
        # Context compaction runs in the worker thread and uses local Ollama only.
        messages = None

        def request_answer() -> str:
            context_messages = self.session_context.build(
                lambda transcript: self.client.summarize(model, transcript)
            )
            return self.agent_runtime.run(model, context_messages)

        def received(answer: str) -> None:
            self.session_context.add("assistant", answer)
            self.audit_log.record_event("assistant_response", {"model": model, "character_count": len(answer)})
            self.chat_view.append(f"<b>Assistant:</b> {self._escape(answer)}")
            self.send_button.setEnabled(True)

        self._background(request_answer, received)

    def _show_error(self, message: str) -> None:
        self.audit_log.record_event("application_error", {"message": message})
        self.status.setText("Ollama request failed.")
        self.refresh_button.setEnabled(True)
        if not self.permission_policy.emergency_stopped:
            self.send_button.setEnabled(True)
        QMessageBox.warning(self, "Local Desktop AI Agent", message)

    def closeEvent(self, event) -> None:
        self.task_scheduler.shutdown(wait_for_tasks=False)
        self.audit_log.record_event("application_exiting")
        super().closeEvent(event)

    @staticmethod
    def _escape(value: str) -> str:
        return (value.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace("\n", "<br>"))
