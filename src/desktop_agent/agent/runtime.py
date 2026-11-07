"""Bounded model/tool loop. Model output is intent, never an execution authority."""

import json
from typing import Any

from desktop_agent.agent.models import ToolCall
from desktop_agent.agent.registry import ToolRegistry
from desktop_agent.ollama.client import OllamaClient, OllamaError


class AgentRuntime:
    def __init__(self, client: OllamaClient, registry: ToolRegistry, max_tool_rounds: int = 4) -> None:
        if not 1 <= max_tool_rounds <= 8:
            raise ValueError("max_tool_rounds must be between 1 and 8")
        self.client = client
        self.registry = registry
        self.max_tool_rounds = max_tool_rounds

    def run(self, model: str, messages: list[dict[str, Any]]) -> str:
        conversation = [dict(message) for message in messages]
        schemas = self.registry.model_schemas()
        for _ in range(self.max_tool_rounds):
            message = self.client.chat_message(model, conversation, schemas or None)
            calls = message.get("tool_calls") or []
            if not calls:
                content = message.get("content", "")
                if not isinstance(content, str):
                    raise OllamaError("Model returned an invalid final response.")
                return content
            # Preserve the assistant tool-call message in the protocol conversation.
            conversation.append(message)
            for item in calls:
                if not isinstance(item, dict):
                    raise OllamaError("Model returned a malformed tool call.")
                function = item.get("function")
                if not isinstance(function, dict) or not isinstance(function.get("name"), str):
                    raise OllamaError("Model returned a tool call without a function name.")
                raw_args = function.get("arguments", {})
                if isinstance(raw_args, str):
                    try:
                        raw_args = json.loads(raw_args)
                    except json.JSONDecodeError as exc:
                        raise OllamaError("Model returned invalid JSON tool arguments.") from exc
                if not isinstance(raw_args, dict):
                    raise OllamaError("Model tool arguments must be a JSON object.")
                call_id = item.get("id")
                try:
                    result = self.registry.execute(ToolCall(
                        tool_name=function["name"],
                        arguments=raw_args,
                        reason="Requested by the local assistant for the current user task.",
                    ))
                    payload = {"ok": True, "result": result}
                except (PermissionError, KeyError, ValueError) as exc:
                    payload = {"ok": False, "error": str(exc)}
                except Exception:
                    # Do not expose tracebacks, local paths, or exception internals to the model.
                    payload = {"ok": False, "error": "Tool execution failed. No success is implied."}
                conversation.append({
                    "role": "tool",
                    "content": json.dumps(payload, ensure_ascii=False, default=str)[:8000],
                    **({"tool_name": function["name"]} if call_id is None else {"tool_call_id": call_id}),
                })
        # Do not silently continue autonomous execution after the bounded tool budget.
        return "I reached the tool-call limit for this turn. Please review the actions completed so far before continuing."
