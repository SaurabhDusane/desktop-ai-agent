"""Tool registry and single enforcement point for permissions and auditing."""

from dataclasses import dataclass
from typing import Any, Callable

from desktop_agent.agent.audit import AuditLog
from desktop_agent.agent.models import RiskLevel, ToolCall
from desktop_agent.agent.policy import ApprovalCallback, Decision, PermissionPolicy


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    risk: RiskLevel
    handler: Callable[..., Any]


class ToolRegistry:
    def __init__(self, policy: PermissionPolicy, audit_log: AuditLog,
                 approval_callback: ApprovalCallback | None = None) -> None:
        self.policy = policy
        self.audit_log = audit_log
        self.approval_callback = approval_callback
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Tool already registered: {spec.name}")
        self._tools[spec.name] = spec

    def descriptions(self) -> list[dict[str, str]]:
        return [
            {"name": spec.name, "description": spec.description, "risk": spec.risk.name.lower()}
            for spec in self._tools.values()
        ]

    def execute(self, call: ToolCall) -> Any:
        spec = self._tools.get(call.tool_name)
        if spec is None:
            raise KeyError(f"Unknown tool: {call.tool_name}")
        policy = self.policy.evaluate(spec.name, spec.risk)
        decision = policy.decision
        if decision is Decision.APPROVAL_REQUIRED:
            approved = bool(
                self.approval_callback
                and self.approval_callback(spec.name, call.reason or spec.description, call.arguments)
            )
            decision = Decision.ALLOW if approved else Decision.DENY
        if decision is not Decision.ALLOW:
            outcome = "blocked" if policy.decision is Decision.DENY else "denied"
            self.audit_log.record(
                tool_name=spec.name, application=call.application, risk=spec.risk.name,
                decision=decision.value, outcome=outcome, arguments=call.arguments,
                detail=policy.explanation,
            )
            raise PermissionError(policy.explanation if outcome == "blocked" else "User did not approve this action.")
        try:
            result = spec.handler(**call.arguments)
        except Exception as exc:
            self.audit_log.record(
                tool_name=spec.name, application=call.application, risk=spec.risk.name,
                decision=decision.value, outcome="error", arguments=call.arguments, detail=str(exc),
            )
            raise
        self.audit_log.record(
            tool_name=spec.name, application=call.application, risk=spec.risk.name,
            decision=decision.value, outcome="success", arguments=call.arguments,
        )
        return result
