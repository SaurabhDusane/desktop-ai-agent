from __future__ import annotations

import pytest

from desktop_agent.agent.audit import AuditLog
from desktop_agent.agent.capabilities import Capability, CapabilityPolicy
from desktop_agent.agent.models import ToolCall
from desktop_agent.agent.policy import PermissionPolicy
from desktop_agent.agent.registry import ToolRegistry
from desktop_agent.desktop.perception import (
    MAX_DESCRIPTION_CHARS, MAX_IMAGE_BYTES, PerceptionBroker, PerceptionError,
)
from desktop_agent.desktop.perception_tools import register_perception_tools


class FakeCapture:
    def __init__(self, data=b"fake-png"):
        self.data = data
        self.calls = 0

    def capture_primary_display(self):
        self.calls += 1
        return self.data


def test_broker_captures_only_when_invoked_and_returns_bounded_result():
    capture = FakeCapture()
    seen = []
    broker = PerceptionBroker(capture, lambda image: seen.append(image) or "  visible window  ")
    assert capture.calls == 0
    result = broker.describe_primary_screen()
    assert capture.calls == 1
    assert seen == [b"fake-png"]
    assert result["description"] == "visible window"
    assert result["retention"].startswith("memory_only")


def test_broker_rejects_oversized_image_before_analysis():
    capture = FakeCapture(b"x" * (MAX_IMAGE_BYTES + 1))
    called = []
    broker = PerceptionBroker(capture, lambda image: called.append(True) or "ignored")
    with pytest.raises(PerceptionError):
        broker.describe_primary_screen()
    assert called == []


def test_broker_bounds_description():
    broker = PerceptionBroker(FakeCapture(), lambda image: "x" * (MAX_DESCRIPTION_CHARS + 100))
    assert len(broker.describe_primary_screen()["description"]) == MAX_DESCRIPTION_CHARS


def test_perception_tool_requires_fresh_approval_and_capture_capability(tmp_path):
    capture = FakeCapture()
    approvals = []
    broker = PerceptionBroker(capture, lambda image: "desktop summary")
    registry = ToolRegistry(
        PermissionPolicy(), AuditLog(tmp_path / "audit.sqlite3"),
        lambda name, reason, args: approvals.append((name, reason)) or True,
        CapabilityPolicy(),
    )
    register_perception_tools(registry, broker)
    result = registry.execute(ToolCall("perception_describe_primary_screen"))
    assert result["description"] == "desktop summary"
    assert capture.calls == 1
    assert len(approvals) == 1
    assert "desktop:capture@primary_display" in approvals[0][1]


def test_perception_denial_does_not_capture(tmp_path):
    capture = FakeCapture()
    broker = PerceptionBroker(capture, lambda image: "should not run")
    registry = ToolRegistry(
        PermissionPolicy(), AuditLog(tmp_path / "audit.sqlite3"),
        lambda *args: False, CapabilityPolicy(),
    )
    register_perception_tools(registry, broker)
    with pytest.raises(PermissionError):
        registry.execute(ToolCall("perception_describe_primary_screen"))
    assert capture.calls == 0


def test_capture_capability_alone_does_not_bypass_sensitive_approval(tmp_path):
    capture = FakeCapture()
    approvals = []
    broker = PerceptionBroker(capture, lambda image: "summary")
    policy = CapabilityPolicy()
    policy.grant(Capability("desktop", frozenset({"capture"}), "primary_display"))
    registry = ToolRegistry(
        PermissionPolicy(), AuditLog(tmp_path / "audit.sqlite3"),
        lambda *args: approvals.append(args) or False, policy,
    )
    register_perception_tools(registry, broker)
    with pytest.raises(PermissionError):
        registry.execute(ToolCall("perception_describe_primary_screen"))
    assert len(approvals) == 1
    assert capture.calls == 0
