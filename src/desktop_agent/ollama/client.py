"""Typed client for the Ollama HTTP API."""

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

    def summarize(self, model: str, transcript: str) -> str:
        """Summarize session context using the configured local Ollama instance."""
        return self.chat(model, [
            {"role": "system", "content": "You are a concise conversation-context compressor. Return only factual reusable context."},
            {"role": "user", "content": transcript},
        ])

    def chat(self, model: str, messages: list[dict[str, str]]) -> str:
        if not model.strip():
            raise OllamaError("Select an Ollama model before sending a message.")
        try:
            response = httpx.post(
                f"{self._base_url}/api/chat",
                json={"model": model, "messages": messages, "stream": False},
                timeout=self._timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise OllamaError(f"Ollama chat request failed: {exc}") from exc
        content = payload.get("message", {}).get("content")
        if not isinstance(content, str):
            raise OllamaError("Ollama returned no message content.")
        return content
