import pytest

from desktop_agent.agent.audit import AuditLog
from desktop_agent.agent.capabilities import Capability, CapabilityPolicy
from desktop_agent.agent.models import RiskLevel, ToolCall
from desktop_agent.agent.policy import PermissionPolicy
from desktop_agent.agent.registry import ToolRegistry, ToolSpec


def test_capability_matching_is_scoped_and_action_specific():
    policy = CapabilityPolicy()
    policy.grant(Capability("filesystem", frozenset({"read"}), "workspace"))
    assert policy.missing((Capability("filesystem", frozenset({"read"}), "workspace"),)) == ()
    assert policy.missing((Capability("filesystem", frozenset({"write"}), "workspace"),))
    assert policy.missing((Capability("filesystem", frozenset({"read"}), "home"),))


def test_wildcard_capability_covers_matching_resource_and_scope():
    policy = CapabilityPolicy((Capability("desktop", frozenset({"observe", "interact"})),))
    assert policy.missing((Capability("desktop", frozenset({"observe"}), "window:42"),)) == ()


def test_revoke_capability_removes_access():
    capability = Capability("application", frozenset({"launch"}), "catalog")
    policy = CapabilityPolicy()
    policy.grant(capability)
    policy.revoke(capability)
    assert policy.missing((capability,)) == (capability,)


def test_missing_capability_requires_explicit_approval(tmp_path):
    executed = []
    approvals = []
    capability = Capability("filesystem", frozenset({"read"}), "workspace")
    policy = CapabilityPolicy()
    registry = ToolRegistry(
        PermissionPolicy(), AuditLog(tmp_path / "audit.db"),
        lambda name, reason, args: approvals.append((name, reason)) or True,
        capability_policy=policy,
    )
    registry.register(ToolSpec(
        "read_workspace", "Read workspace", RiskLevel.READ_ONLY,
        lambda: executed.append(True) or "read",
        {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        (capability,),
    ))
    assert registry.execute(ToolCall("read_workspace")) == "read"
    assert executed == [True]
    assert len(approvals) == 1
    # The approval was for one invocation; it did not persist as a capability grant.
    assert policy.missing((capability,)) == (capability,)


def test_missing_capability_denial_blocks_handler(tmp_path):
    executed = []
    capability = Capability("application", frozenset({"launch"}), "catalog")
    registry = ToolRegistry(
        PermissionPolicy(), AuditLog(tmp_path / "audit.db"),
        lambda *_: False,
        capability_policy=CapabilityPolicy(),
    )
    registry.register(ToolSpec(
        "launch", "Launch app", RiskLevel.READ_ONLY, lambda: executed.append(True),
        {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        (capability,),
    ))
    with pytest.raises(PermissionError, match="capability"):
        registry.execute(ToolCall("launch"))
    assert executed == []
