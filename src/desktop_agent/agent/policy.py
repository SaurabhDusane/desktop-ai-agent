"""Central permission policy. Tool implementations never decide their own trust level."""

from dataclasses import dataclass
from enum import Enum
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
    """Conservative defaults; session grants are explicit and never persisted."""

    def __init__(self, max_auto_risk: RiskLevel = RiskLevel.ROUTINE) -> None:
        self.max_auto_risk = max_auto_risk
        self._session_grants: set[str] = set()

    def evaluate(self, tool_name: str, risk: RiskLevel) -> PolicyDecision:
        if risk is RiskLevel.RESTRICTED:
            return PolicyDecision(Decision.DENY, "This action is blocked by the application safety policy.")
        if tool_name in self._session_grants:
            return PolicyDecision(Decision.ALLOW, "Approved for this session by the user.")
        if risk <= self.max_auto_risk:
            return PolicyDecision(Decision.ALLOW, "Within the current automatic permission level.")
        return PolicyDecision(Decision.APPROVAL_REQUIRED, "This action changes system or user data and needs approval.")

    def grant_for_session(self, tool_name: str) -> None:
        if not tool_name.strip():
            raise ValueError("Tool name cannot be empty")
        self._session_grants.add(tool_name)

    def revoke_session_grant(self, tool_name: str) -> None:
        self._session_grants.discard(tool_name)


ApprovalCallback = Callable[[str, str, dict], bool]
