import pytest

from desktop_agent.agent.models import RiskLevel
from desktop_agent.agent.policy import Decision, PermissionPolicy


def test_emergency_stop_denies_even_read_only_tools():
    policy = PermissionPolicy()
    policy.activate_emergency_stop()
    assert policy.evaluate("read", RiskLevel.READ_ONLY).decision is Decision.DENY


def test_emergency_stop_revokes_session_grants():
    policy = PermissionPolicy()
    policy.grant_for_session("change")
    policy.activate_emergency_stop()
    policy.reset_emergency_stop()
    assert policy.evaluate("change", RiskLevel.SYSTEM_CHANGE).decision is Decision.APPROVAL_REQUIRED


def test_read_only_mode_denies_state_changes_but_allows_reads():
    policy = PermissionPolicy()
    policy.set_read_only(True)
    assert policy.evaluate("read", RiskLevel.READ_ONLY).decision is Decision.ALLOW
    assert policy.evaluate("write", RiskLevel.ROUTINE).decision is Decision.DENY


def test_cannot_grant_session_permission_in_read_only_mode():
    policy = PermissionPolicy()
    policy.set_read_only(True)
    with pytest.raises(RuntimeError):
        policy.grant_for_session("change")
