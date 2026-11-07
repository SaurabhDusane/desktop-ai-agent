"""Main-thread approval bridge for tool calls originating in worker threads."""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QMessageBox


@dataclass
class ApprovalRequest:
    tool_name: str
    reason: str
    arguments: dict[str, Any]
    completed: threading.Event = field(default_factory=threading.Event)
    approved: bool = False


class ApprovalBroker(QObject):
    """Synchronous policy callback that presents confirmations on the Qt UI thread."""

    requested = Signal(object)
    approval_state = Signal(str, bool)

    def __init__(self, parent: QObject | None = None, timeout_seconds: float = 120.0) -> None:
        super().__init__(parent)
        self.timeout_seconds = timeout_seconds
        self.requested.connect(self._present)

    def approve(self, tool_name: str, reason: str, arguments: dict) -> bool:
        request = ApprovalRequest(tool_name, reason, arguments)
        self.approval_state.emit(tool_name, True)
        try:
            if QThread.currentThread() == self.thread():
                self._present(request)
            else:
                self.requested.emit(request)
            if not request.completed.wait(self.timeout_seconds):
                return False
            return request.approved
        finally:
            self.approval_state.emit(tool_name, False)

    def _present(self, request: ApprovalRequest) -> None:
        try:
            details = json.dumps(request.arguments, indent=2, ensure_ascii=False, default=str)
            box = QMessageBox()
            box.setIcon(QMessageBox.Icon.Warning)
            box.setWindowTitle("Desktop action approval")
            box.setText(f"Allow this desktop action?\\n\\n{request.tool_name}")
            box.setInformativeText(request.reason or "No reason was provided.")
            box.setDetailedText(details[:12_000])
            box.setStandardButtons(
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            box.setDefaultButton(QMessageBox.StandardButton.No)
            request.approved = box.exec() == QMessageBox.StandardButton.Yes
        finally:
            request.completed.set()
