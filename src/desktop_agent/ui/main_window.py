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
        # The approval callback marshals confirmations onto the Qt main thread.
        self.approval_broker = ApprovalBroker(self)
        audit_path = Path.home() / ".local-desktop-agent" / "audit.sqlite3"
        self.tool_registry = ToolRegistry(
            PermissionPolicy(), AuditLog(audit_path), self.approval_broker.approve
        )
        self.desktop_tools_available = False
        if sys.platform == "win32":
            from desktop_agent.desktop.tools import register_uia_tools
            register_uia_tools(self.tool_registry)
            self.desktop_tools_available = True
        self.history: list[dict[str, str]] = []
        self._threads: list[QThread] = []
        self.setWindowTitle("Local Desktop AI Agent")
        self.resize(900, 650)

        self.model_box = QComboBox()
        self.refresh_button = QPushButton("Refresh models")
        self.status = QLabel("Connecting to local Ollama…")
        self.chat_view = QTextBrowser()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Message your local model…")
        self.send_button = QPushButton("Send")

        header = QHBoxLayout()
        header.addWidget(QLabel("Model:"))
        header.addWidget(self.model_box, 1)
        header.addWidget(self.refresh_button)
        composer = QHBoxLayout()
        composer.addWidget(self.input, 1)
        composer.addWidget(self.send_button)
        layout = QVBoxLayout()
        layout.addLayout(header)
        layout.addWidget(self.status)
        layout.addWidget(self.chat_view, 1)
        layout.addLayout(composer)
        root = QWidget()
        root.setLayout(layout)
        self.setCentralWidget(root)

        self.refresh_button.clicked.connect(self.refresh_models)
        self.send_button.clicked.connect(self.send_message)
        self.input.returnPressed.connect(self.send_message)
        self.refresh_models()

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
        self.input.clear()
        self.send_button.setEnabled(False)
        self.chat_view.append(f"<b>You:</b> {self._escape(prompt)}")
        messages = [*self.history, {"role": "user", "content": prompt}]

        def received(answer: str) -> None:
            self.history.extend([
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": answer},
            ])
            self.chat_view.append(f"<b>Assistant:</b> {self._escape(answer)}")
            self.send_button.setEnabled(True)

        self._background(lambda: self.client.chat(model, messages), received)

    def _show_error(self, message: str) -> None:
        self.status.setText("Ollama request failed.")
        self.refresh_button.setEnabled(True)
        self.send_button.setEnabled(True)
        QMessageBox.warning(self, "Local Desktop AI Agent", message)

    @staticmethod
    def _escape(value: str) -> str:
        return (value.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace("\n", "<br>"))
