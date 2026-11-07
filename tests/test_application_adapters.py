import pytest
from desktop_agent.agent.capabilities import Capability
from desktop_agent.agent.models import RiskLevel
from desktop_agent.desktop.adapters import AdapterDescriptor, AdapterOperation, AdapterRegistry

class FakeAdapter:
    descriptor = AdapterDescriptor("fake_app", "Fake App", "test", "Test adapter.")
    operations = (AdapterOperation("read_status", "Read status.", RiskLevel.READ_ONLY,
        {"type": "object", "properties": {"detail": {"type": "string"}},
         "required": [], "additionalProperties": False},
        (Capability("fake_app", frozenset({"read"}), "status"),)),)
    def __init__(self):
        self.calls = []
    def execute(self, operation, arguments):
        self.calls.append((operation, arguments))
        return {"status": "ok"}

def test_registry_dispatches_only_declared_operations():
    registry, adapter = AdapterRegistry(), FakeAdapter()
    registry.register(adapter)
    assert registry.invoke("fake_app", "read_status", {"detail": "short"}) == {"status": "ok"}
    assert adapter.calls == [("read_status", {"detail": "short"})]

def test_unknown_adapter_and_operation_fail_closed():
    registry = AdapterRegistry()
    registry.register(FakeAdapter())
    with pytest.raises(KeyError, match="Unknown application adapter"):
        registry.invoke("unknown", "read_status", {})
    with pytest.raises(KeyError, match="does not declare"):
        registry.invoke("fake_app", "run_shell", {})

def test_adapter_rejects_unknown_and_missing_arguments():
    registry = AdapterRegistry()
    registry.register(FakeAdapter())
    with pytest.raises(ValueError, match="unknown"):
        registry.invoke("fake_app", "read_status", {"detail": "x", "extra": True})
    with pytest.raises(ValueError, match="missing"):
        registry.invoke("fake_app", "read_status", {"unexpected": "x"})

def test_duplicate_adapter_rejected():
    registry, adapter = AdapterRegistry(), FakeAdapter()
    registry.register(adapter)
    with pytest.raises(ValueError, match="duplicate"):
        registry.register(adapter)
