"""Tool registry: schema validation, policy enforcement, approval, and audit."""

from dataclasses import dataclass
import inspect
from typing import Any, Callable

from desktop_agent.agent.audit import AuditLog
from desktop_agent.agent.capabilities import Capability, CapabilityPolicy
from desktop_agent.agent.models import RiskLevel, ToolCall
from desktop_agent.agent.policy import ApprovalCallback, Decision, PermissionPolicy


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    risk: RiskLevel
    handler: Callable[..., Any]
    input_schema: dict[str, Any] | None = None
    capabilities: tuple[Capability, ...] = ()


class ToolRegistry:
    """The only supported path from model-proposed calls to side effects."""

    def __init__(self, policy: PermissionPolicy, audit_log: AuditLog,
                 approval_callback: ApprovalCallback | None = None,
                 capability_policy: CapabilityPolicy | None = None) -> None:
        self.policy = policy
        self.audit_log = audit_log
        self.approval_callback = approval_callback
        self.capability_policy = capability_policy or CapabilityPolicy((Capability('desktop', frozenset({'observe'})),))
        self._tools: dict[str, ToolSpec] = {}

    def grant_capability(self, capability: Capability) -> None:
        if self.policy.emergency_stopped or self.policy.read_only:
            raise RuntimeError("Cannot grant capabilities while a safety mode is active.")
        self.capability_policy.grant(capability)
        self.audit_log.record_event("capability_granted", {
            "resource": capability.resource, "actions": sorted(capability.actions),
            "scope": capability.scope,
        })

    def revoke_capability(self, capability: Capability) -> None:
        self.capability_policy.revoke(capability)
        self.audit_log.record_event("capability_revoked", {
            "resource": capability.resource, "actions": sorted(capability.actions),
            "scope": capability.scope,
        })

    def revoke_all_capabilities(self) -> None:
        self.capability_policy.revoke_all()
        self.audit_log.record_event("all_capabilities_revoked")

    def register(self, spec: ToolSpec) -> None:
        if not spec.name or spec.name in self._tools:
            raise ValueError(f"Invalid or duplicate tool name: {spec.name}")
        self._tools[spec.name] = spec

    def descriptions(self) -> list[dict[str, str]]:
        return [
            {"name": spec.name, "description": spec.description, "risk": spec.risk.name.lower()}
            for spec in self._tools.values()
        ]

    def model_schemas(self) -> list[dict[str, Any]]:
        """Return Ollama/OpenAI-compatible function schemas for registered tools only."""
        return [{
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.input_schema or self._inferred_schema(spec.handler),
            },
        } for spec in self._tools.values()]

    @staticmethod
    def _inferred_schema(handler: Callable[..., Any]) -> dict[str, Any]:
        signature = inspect.signature(handler)
        properties: dict[str, Any] = {}
        required: list[str] = []
        for name, parameter in signature.parameters.items():
            if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
                raise ValueError("Tool handlers may not use variadic arguments")
            annotation = parameter.annotation
            kind = "string" if annotation is str else "integer" if annotation is int else (
                "boolean" if annotation is bool else "number" if annotation is float else "string"
            )
            properties[name] = {"type": kind}
            if parameter.default is inspect.Parameter.empty:
                required.append(name)
        return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}

    def _validate_arguments(self, spec: ToolSpec, arguments: Any) -> dict[str, Any]:
        if not isinstance(arguments, dict):
            raise ValueError("Tool arguments must be a JSON object.")
        schema = spec.input_schema or self._inferred_schema(spec.handler)
        if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
            raise ValueError(f"Tool {spec.name} must declare a closed object schema.")
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        unknown = set(arguments) - set(properties)
        missing = set(required) - set(arguments)
        if unknown or missing:
            raise ValueError(f"Invalid arguments for {spec.name}; unknown={sorted(unknown)}, missing={sorted(missing)}")
        for key, value in arguments.items():
            rule = properties[key]
            expected = rule.get("type")
            valid = (
                expected == "string" and isinstance(value, str)
                or expected == "integer" and isinstance(value, int) and not isinstance(value, bool)
                or expected == "number" and isinstance(value, (int, float)) and not isinstance(value, bool)
                or expected == "boolean" and isinstance(value, bool)
                or expected == "array" and isinstance(value, list)
                or expected == "object" and isinstance(value, dict)
            )
            if not valid:
                raise ValueError(f"Argument {key!r} for {spec.name} must be {expected}.")
            if isinstance(value, str) and len(value) > int(rule.get("maxLength", 10000)):
                raise ValueError(f"Argument {key!r} exceeds its maximum length.")
            if "enum" in rule and value not in rule["enum"]:
                raise ValueError(f"Argument {key!r} is not an allowed value.")
        return arguments

    def execute(self, call: ToolCall) -> Any:
        spec = self._tools.get(call.tool_name)
        if spec is None:
            raise KeyError(f"Unknown tool: {call.tool_name}")
        arguments = self._validate_arguments(spec, call.arguments)

        # Combine capability and risk requirements into one approval decision.
        missing_capabilities = self.capability_policy.missing(spec.capabilities)
        policy = self.policy.evaluate(spec.name, spec.risk)
        if policy.decision is Decision.DENY:
            self.audit_log.record(
                tool_name=spec.name, application=call.application, risk=spec.risk.name,
                decision=Decision.DENY.value, outcome="blocked", arguments=arguments,
                detail=policy.explanation,
            )
            raise PermissionError(policy.explanation)

        approval_reasons: list[str] = []
        if missing_capabilities:
            approval_reasons.append(
                "Missing capabilities: " + ", ".join(
                    f"{cap.resource}:{','.join(sorted(cap.actions))}@{cap.scope}"
                    for cap in missing_capabilities
                )
            )
        if policy.decision is Decision.APPROVAL_REQUIRED:
            approval_reasons.append(call.reason or policy.explanation)

        approved_once = False
        if approval_reasons:
            reason = " | ".join(approval_reasons)
            approved_once = bool(
                self.approval_callback
                and self.approval_callback(spec.name, reason, arguments)
            )
            if not approved_once:
                self.audit_log.record(
                    tool_name=spec.name, application=call.application, risk=spec.risk.name,
                    decision=Decision.DENY.value, outcome="denied", arguments=arguments,
                    detail="User did not approve the complete action and capability request.",
                )
                raise PermissionError("User did not approve this action.")

        # Revalidate inputs and re-check current safety state immediately before
        # invoking the handler. A one-shot capability approval is not persisted.
        arguments = self._validate_arguments(spec, arguments)
        final_policy = self.policy.evaluate(spec.name, spec.risk)
        final_missing = self.capability_policy.missing(spec.capabilities)
        if final_policy.decision is Decision.DENY:
            detail = final_policy.explanation
            outcome = "blocked"
        elif final_missing and not approved_once:
            detail = "Required capability was revoked before execution."
            outcome = "blocked"
        elif final_policy.decision is Decision.APPROVAL_REQUIRED and not approved_once:
            detail = final_policy.explanation
            outcome = "blocked"
        else:
            detail = ""
            outcome = ""

        if outcome:
            self.audit_log.record(
                tool_name=spec.name, application=call.application, risk=spec.risk.name,
                decision=Decision.DENY.value, outcome=outcome, arguments=arguments,
                detail=detail,
            )
            raise PermissionError(detail)

        try:
            result = spec.handler(**arguments)
        except Exception as exc:
            self.audit_log.record(
                tool_name=spec.name, application=call.application, risk=spec.risk.name,
                decision=Decision.ALLOW.value, outcome="error", arguments=arguments, detail=str(exc),
            )
            raise
        self.audit_log.record(
            tool_name=spec.name, application=call.application, risk=spec.risk.name,
            decision=Decision.ALLOW.value, outcome="success", arguments=arguments,
        )
        return result
