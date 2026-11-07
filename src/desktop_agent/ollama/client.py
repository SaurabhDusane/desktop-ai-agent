"""Typed client for the local Ollama chat and tool-calling API."""

from typing import Any

import httpx


class OllamaError(RuntimeError):
    """Raised when Ollama is unavailable or returns an invalid response."""


class OllamaClient:
    def __init__(self, base_url: str, timeout_seconds: float = 120.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    def list_models(self) -> list[str]:
        try:
            response = httpx.get(f"{self._base_url}/api/tags", timeout=10.0)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise OllamaError(f"Could not reach Ollama at {self._base_url}: {exc}") from exc
        return sorted(model["name"] for model in payload.get("models", []) if model.get("name"))


    def model_details(self, model: str) -> dict[str, Any]:
        """Read local Ollama model metadata without loading or modifying the model."""
        try:
            response = httpx.post(f"{self._base_url}/api/show", json={"model": model},
                                  timeout=15.0)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise OllamaError(f"Could not inspect local model {model}: {exc}") from exc
        if not isinstance(payload, dict):
            raise OllamaError("Ollama returned invalid model metadata.")
        return payload

    def running_models(self) -> list[dict[str, Any]]:
        """Return Ollama's currently loaded models and reported memory sizes."""
        try:
            response = httpx.get(f"{self._base_url}/api/ps", timeout=10.0)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise OllamaError(f"Could not inspect running Ollama models: {exc}") from exc
        models = payload.get("models", []) if isinstance(payload, dict) else []
        if not isinstance(models, list):
            raise OllamaError("Ollama returned invalid running-model data.")
        return [item for item in models if isinstance(item, dict)]

    def summarize(self, model: str, transcript: str) -> str:
        return self.chat(model, [
            {"role": "system", "content": "You are a concise conversation-context compressor. Return only factual reusable context."},
            {"role": "user", "content": transcript},
        ])

    def chat(self, model: str, messages: list[dict[str, Any]]) -> str:
        result = self.chat_message(model, messages)
        content = result.get("content")
        if not isinstance(content, str):
            raise OllamaError("Ollama returned no message content.")
        return content

    def chat_message(
        self, model: str, messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Return the assistant message, including any native Ollama tool_calls."""
        if not model.strip():
            raise OllamaError("Select an Ollama model before sending a message.")
        body: dict[str, Any] = {"model": model, "messages": messages, "stream": False}
        if tools:
            body["tools"] = tools
        try:
            response = httpx.post(
                f"{self._base_url}/api/chat", json=body, timeout=self._timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise OllamaError(f"Ollama chat request failed: {exc}") from exc
        message = payload.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content", ""), str):
            raise OllamaError("Ollama returned an invalid assistant message.")
        calls = message.get("tool_calls", [])
        if not isinstance(calls, list):
            raise OllamaError("Ollama returned malformed tool calls.")
        return message
