
from desktop_agent.agent.audit import AuditLog
from desktop_agent.agent.models import RiskLevel
from desktop_agent.agent.policy import PermissionPolicy
from desktop_agent.agent.registry import ToolRegistry, ToolSpec
from desktop_agent.agent.runtime import AgentRuntime


class FakeClient:
    def __init__(self, messages):
        self.messages = iter(messages)
        self.tools_seen = []

    def chat_message(self, model, messages, tools=None):
        self.tools_seen.append(tools)
        return next(self.messages)


def test_runtime_routes_model_tool_call_through_registry(tmp_path):
    seen = []
    registry = ToolRegistry(PermissionPolicy(), AuditLog(tmp_path / "audit.db"))
    registry.register(ToolSpec(
        "read_value", "Read a value", RiskLevel.READ_ONLY,
        lambda key: seen.append(key) or {"value": key},
        {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"], "additionalProperties": False},
    ))
    client = FakeClient([
        {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "read_value", "arguments": {"key": "status"}}}
        ]},
        {"role": "assistant", "content": "The status is available."},
    ])
    answer = AgentRuntime(client, registry).run("local-model", [{"role": "user", "content": "check"}])
    assert answer == "The status is available."
    assert seen == ["status"]
    assert client.tools_seen[0][0]["function"]["name"] == "read_value"


def test_runtime_rejects_malformed_json_arguments_without_execution(tmp_path):
    seen = []
    registry = ToolRegistry(PermissionPolicy(), AuditLog(tmp_path / "audit.db"))
    registry.register(ToolSpec(
        "read_value", "Read a value", RiskLevel.READ_ONLY, lambda: seen.append(True),
        {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    ))
    client = FakeClient([
        {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "read_value", "arguments": "{not-json"}}
        ]}
    ])
    try:
        AgentRuntime(client, registry).run("local-model", [{"role": "user", "content": "do it"}])
    except Exception as exc:
        assert "invalid JSON" in str(exc)
    else:
        raise AssertionError("Malformed arguments should fail closed")
    assert seen == []


def test_runtime_bounds_tool_rounds(tmp_path):
    registry = ToolRegistry(PermissionPolicy(), AuditLog(tmp_path / "audit.db"))
    registry.register(ToolSpec(
        "read_value", "Read a value", RiskLevel.READ_ONLY, lambda: "ok",
        {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    ))
    repeated = {"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": "read_value", "arguments": {}}}
    ]}
    client = FakeClient([repeated, repeated])
    result = AgentRuntime(client, registry, max_tool_rounds=2).run("local-model", [{"role": "user", "content": "loop"}])
    assert "tool-call limit" in result


def test_runtime_executes_model_tool_calls_through_scheduler(tmp_path):
    from desktop_agent.agent.scheduler import TaskScheduler, TaskState

    seen = []
    events = []
    registry = ToolRegistry(PermissionPolicy(), AuditLog(tmp_path / "audit.db"))
    registry.register(ToolSpec(
        "read_value", "Read a value", RiskLevel.READ_ONLY,
        lambda key: seen.append(key) or {"value": key},
        {"type": "object", "properties": {"key": {"type": "string"}},
         "required": ["key"], "additionalProperties": False},
    ))
    client = FakeClient([
        {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "read_value", "arguments": {"key": "dashboard"}}}
        ]},
        {"role": "assistant", "content": "Read completed."},
    ])
    scheduler = TaskScheduler(registry, event_callback=events.append)
    try:
        answer = AgentRuntime(client, registry, scheduler=scheduler).run(
            "local-model", [{"role": "user", "content": "read"}]
        )
        assert answer == "Read completed."
        assert seen == ["dashboard"]
        assert {event.state for event in events} >= {
            TaskState.QUEUED, TaskState.RUNNING, TaskState.COMPLETED,
        }
        assert scheduler.metrics().completed_plans == 1
    finally:
        scheduler.shutdown()
