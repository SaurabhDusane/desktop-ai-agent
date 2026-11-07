import platform

import pytest

from desktop_agent.desktop.uia import WindowsUIAutomation


@pytest.mark.skipif(platform.system() != "Windows", reason="Requires an interactive Windows desktop")
def test_windows_uia_can_enumerate_desktop_windows():
    pytest.importorskip("pywinauto")
    adapter = WindowsUIAutomation()
    windows = adapter.list_windows()
    assert isinstance(windows, list)
    assert all({"title", "process_id", "handle", "control_type"} <= set(item) for item in windows)
