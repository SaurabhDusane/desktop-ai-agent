"""Conservative Windows UI Automation adapter built on pywinauto's UIA backend.

This module imports pywinauto lazily so the package and its unit tests remain
importable on non-Windows CI hosts.
"""
from __future__ import annotations

import platform
from typing import Any


class DesktopAutomationError(RuntimeError):
    """A desktop operation could not be completed safely."""


class WindowsUIAutomation:
    def __init__(self, desktop_factory=None) -> None:
        if platform.system() != "Windows":
            raise DesktopAutomationError("Windows UI Automation is available on Windows only.")
        if desktop_factory is None:
            try:
                from pywinauto import Desktop
            except ImportError as exc:
                raise DesktopAutomationError(
                    "Install the Windows automation extra: pip install -e '.[windows]'"
                ) from exc
            desktop_factory = Desktop
        self._desktop_factory = desktop_factory

    def _desktop(self):
        return self._desktop_factory(backend="uia")

    def list_windows(self) -> list[dict[str, Any]]:
        """Return visible top-level windows; omit control text and values."""
        try:
            windows = self._desktop().windows()
            result = []
            for window in windows:
                try:
                    if not window.is_visible():
                        continue
                    info = window.element_info
                    result.append({
                        "title": (info.name or "")[:200],
                        "process_id": int(info.process_id or 0),
                        "handle": int(info.handle or 0),
                        "control_type": str(info.control_type or "Window"),
                    })
                except Exception:
                    continue
            return result
        except Exception as exc:
            raise DesktopAutomationError(f"Could not enumerate desktop windows: {exc}") from exc

    def inspect_controls(
        self, title: str, process_id: int | None = None,
        max_depth: int = 2, max_nodes: int = 80,
    ) -> list[dict[str, Any]]:
        """Inspect a bounded control tree; never read edit values or document contents."""
        self._validate_limits(max_depth, max_nodes)
        window = self._find_window(title, process_id)
        try:
            root = window.element_info
            found: list[dict[str, Any]] = []
            queue = [(root, 0)]
            while queue and len(found) < max_nodes:
                node, depth = queue.pop(0)
                found.append({
                    "name": (node.name or "")[:160],
                    "control_type": str(node.control_type or "")[:60],
                    "automation_id": str(node.automation_id or "")[:120],
                    "depth": depth,
                })
                if depth < max_depth:
                    try:
                        queue.extend((child, depth + 1) for child in node.children())
                    except Exception:
                        pass
            return found
        except Exception as exc:
            raise DesktopAutomationError(f"Could not inspect controls: {exc}") from exc

    def focus_window(self, title: str, process_id: int | None = None) -> dict[str, Any]:
        window = self._find_window(title, process_id)
        try:
            window.set_focus()
            return {"focused": title, "process_id": process_id}
        except Exception as exc:
            raise DesktopAutomationError(f"Could not focus window {title!r}: {exc}") from exc

    def click_control(
        self, title: str, control_type: str, automation_id: str = "",
        name: str = "", process_id: int | None = None,
    ) -> dict[str, Any]:
        """Click exactly one uniquely matched control; ambiguous matches fail closed."""
        window = self._find_window(title, process_id)
        matches = self._find_controls(window, control_type, automation_id, name)
        if len(matches) != 1:
            raise DesktopAutomationError(f"Expected exactly one matching control; found {len(matches)}.")
        try:
            matches[0].click()
            return {"clicked": True, "control_type": control_type, "name": name}
        except Exception as exc:
            raise DesktopAutomationError(f"Control click failed: {exc}") from exc

    def type_text(
        self, title: str, control_type: str, text: str,
        automation_id: str = "", name: str = "", process_id: int | None = None,
    ) -> dict[str, Any]:
        """Set text in exactly one matched control. This can submit data only if app semantics do so."""
        if len(text) > 10_000:
            raise DesktopAutomationError("Text input exceeds the 10,000 character limit.")
        window = self._find_window(title, process_id)
        matches = self._find_controls(window, control_type, automation_id, name)
        if len(matches) != 1:
            raise DesktopAutomationError(f"Expected exactly one matching control; found {len(matches)}.")
        try:
            matches[0].set_edit_text(text)
            return {"text_entered": True, "character_count": len(text)}
        except Exception as exc:
            raise DesktopAutomationError(f"Text entry failed: {exc}") from exc

    @staticmethod
    def _validate_limits(max_depth: int, max_nodes: int) -> None:
        if not 0 <= max_depth <= 5 or not 1 <= max_nodes <= 200:
            raise DesktopAutomationError("Inspection limits must be depth 0–5 and 1–200 nodes.")

    def _find_window(self, title: str, process_id: int | None = None):
        if not title or len(title) > 200:
            raise DesktopAutomationError("A non-empty exact window title (max 200 chars) is required.")
        candidates = []
        for window in self._desktop().windows():
            try:
                info = window.element_info
                if info.name == title and window.is_visible():
                    if process_id is None or int(info.process_id or 0) == process_id:
                        candidates.append(window)
            except Exception:
                continue
        if len(candidates) != 1:
            raise DesktopAutomationError(
                f"Expected exactly one visible window match; found {len(candidates)}. "
                "Provide a process ID if titles are duplicated."
            )
        return candidates[0]

    @staticmethod
    def _find_controls(window, control_type: str, automation_id: str, name: str):
        if not control_type or not (automation_id or name):
            raise DesktopAutomationError("Specify control_type and automation_id or exact name.")
        criteria = {"control_type": control_type}
        if automation_id:
            criteria["auto_id"] = automation_id
        if name:
            criteria["title"] = name
        return window.descendants(**criteria)
