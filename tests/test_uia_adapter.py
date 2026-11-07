import pytest

from desktop_agent.desktop.uia import DesktopAutomationError, WindowsUIAutomation


class Info:
    name = "Editor"
    process_id = 42
    handle = 123
    control_type = "Window"
    automation_id = ""

    def children(self):
        return []


class Window:
    element_info = Info()

    def is_visible(self):
        return True

    def set_focus(self):
        self.focused = True

    def descendants(self, **criteria):
        return [FakeControl()]


class FakeControl:
    def click(self):
        self.clicked = True

    def set_edit_text(self, text):
        self.text = text


class FakeDesktop:
    def __init__(self, backend):
        assert backend == "uia"

    def windows(self):
        return [Window()]


def test_adapter_can_be_imported_and_injected_on_ci(monkeypatch):
    monkeypatch.setattr("desktop_agent.desktop.uia.platform.system", lambda: "Windows")
    adapter = WindowsUIAutomation(FakeDesktop)
    assert adapter.list_windows()[0]["title"] == "Editor"


def test_exact_window_focus(monkeypatch):
    monkeypatch.setattr("desktop_agent.desktop.uia.platform.system", lambda: "Windows")
    adapter = WindowsUIAutomation(FakeDesktop)
    assert adapter.focus_window("Editor", 42)["focused"] == "Editor"


def test_control_inspection_is_bounded(monkeypatch):
    monkeypatch.setattr("desktop_agent.desktop.uia.platform.system", lambda: "Windows")
    adapter = WindowsUIAutomation(FakeDesktop)
    controls = adapter.inspect_controls("Editor", max_depth=1, max_nodes=5)
    assert controls[0]["control_type"] == "Window"


def test_rejects_ambiguous_or_missing_control_identity(monkeypatch):
    monkeypatch.setattr("desktop_agent.desktop.uia.platform.system", lambda: "Windows")
    adapter = WindowsUIAutomation(FakeDesktop)
    with pytest.raises(DesktopAutomationError, match="control_type"):
        adapter.click_control("Editor", "")
