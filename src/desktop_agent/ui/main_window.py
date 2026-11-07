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
from desktop_agent.ui.approval import ApprovalBroker


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
        self.audit_log.record_event("application_started", {"platform": sys.platform})
        self.desktop_tools_available = False
        self.desktop_tools_error: str | None = None
        if sys.platform == "win32":
            try:
                from desktop_agent.desktop.tools import register_uia_tools
                register_uia_tools(self.tool_registry)
                self.desktop_tools_available = True
                self.audit_log.record_event("desktop_tools_registered")
            except Exception as exc:
                self.desktop_tools_error = str(exc)
                self.audit_log.record_event("desktop_tools_unavailable", {"error": str(exc)})
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

        def loaded(models: list[str]) -> None:
            self.model_box.clear()
            self.model_box.addItems(models)
            selected = self.model_box.currentText()
            self.audit_log.record_event("model_list_refreshed", {"count": len(models), "selected_model": selected})
            self.status.setText(
                f"{len(models)} model(s) available." if models
                else "Ollama is running, but no models are installed. Pull a model with Ollama."
            )
            self.refresh_button.setEnabled(True)

        self._background(self.client.list_models, loaded)

    def send_message(self) -> None:
        prompt = self.input.text().strip()
        model = self.model_box.currentText()
        if not prompt:
            return
        if not model:
            self._show_error("No model selected. Install a model in Ollama, then refresh.")
            return
        self.audit_log.record_event("user_message", {"model": model, "content": prompt})
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
            return self.client.chat(model, context_messages)

        def received(answer: str) -> None:
            self.session_context.add("assistant", answer)
            self.audit_log.record_event("assistant_response", {"model": model, "content": answer})
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
        self.audit_log.record_event("application_exiting")
        super().closeEvent(event)

    @staticmethod
    def _escape(value: str) -> str:
        return (value.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace("\n", "<br>"))
