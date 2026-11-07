"""Central permission policy with emergency-stop and read-only controls."""

from dataclasses import dataclass
from enum import Enum
from threading import RLock
from typing import Callable

from desktop_agent.agent.models import RiskLevel


class Decision(str, Enum):
    ALLOW = "allow"
    APPROVAL_REQUIRED = "approval_required"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    decision: Decision
    explanation: str


class PermissionPolicy:
    """Conservative defaults; safety modes are enforced centrally."""

    def __init__(self, max_auto_risk: RiskLevel = RiskLevel.ROUTINE) -> None:
        self.max_auto_risk = max_auto_risk
        self._session_grants: set[str] = set()
        self._lock = RLock()
        self._emergency_stopped = False
        self._read_only = False

    @property
    def emergency_stopped(self) -> bool:
        with self._lock:
            return self._emergency_stopped

    @property
    def read_only(self) -> bool:
        with self._lock:
            return self._read_only

    def activate_emergency_stop(self) -> None:
        with self._lock:
            self._emergency_stopped = True
            self._session_grants.clear()

    def reset_emergency_stop(self) -> None:
        with self._lock:
            self._emergency_stopped = False

    def set_read_only(self, enabled: bool) -> None:
        with self._lock:
            self._read_only = bool(enabled)
            if enabled:
                self._session_grants.clear()

    def revoke_all_session_grants(self) -> None:
        with self._lock:
            self._session_grants.clear()

    def evaluate(self, tool_name: str, risk: RiskLevel) -> PolicyDecision:
        with self._lock:
            if self._emergency_stopped:
                return PolicyDecision(Decision.DENY, "Emergency stop is active; all tool execution is disabled.")
            if risk is RiskLevel.RESTRICTED:
                return PolicyDecision(Decision.DENY, "This action is blocked by the application safety policy.")
            if self._read_only and risk > RiskLevel.READ_ONLY:
                return PolicyDecision(Decision.DENY, "Read-only mode blocks all state-changing actions.")
            if risk is RiskLevel.SENSITIVE:
                return PolicyDecision(Decision.APPROVAL_REQUIRED, "This sensitive action requires explicit approval each time.")
            if tool_name in self._session_grants:
                return PolicyDecision(Decision.ALLOW, "Approved for this session by the user.")
            if risk <= self.max_auto_risk:
                return PolicyDecision(Decision.ALLOW, "Within the current automatic permission level.")
            return PolicyDecision(Decision.APPROVAL_REQUIRED, "This action changes system or user data and needs approval.")

    def grant_for_session(self, tool_name: str) -> None:
        if not tool_name.strip():
            raise ValueError("Tool name cannot be empty")
        with self._lock:
            if self._emergency_stopped or self._read_only:
                raise RuntimeError("Cannot grant permissions while safety mode is active.")
            self._session_grants.add(tool_name)

    def revoke_session_grant(self, tool_name: str) -> None:
        with self._lock:
            self._session_grants.discard(tool_name)


ApprovalCallback = Callable[[str, str, dict], bool]
