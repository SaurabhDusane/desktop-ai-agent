"""Opt-in smoke test for a real interactive Windows desktop session."""

import os
import platform

import pytest

from desktop_agent.desktop.uia import WindowsUIAutomation


@pytest.mark.skipif(
    platform.system() != "Windows" or os.getenv("DESKTOP_AGENT_RUN_UIA_SMOKE") != "1",
    reason="Set DESKTOP_AGENT_RUN_UIA_SMOKE=1 in an interactive Windows session",
)
def test_windows_uia_can_enumerate_desktop_windows():
    pytest.importorskip("pywinauto")
    adapter = WindowsUIAutomation()
    windows = adapter.list_windows()
    assert isinstance(windows, list)
    assert all({"title", "process_id", "handle", "control_type"} <= set(item) for item in windows)
