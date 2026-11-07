import httpx
import pytest
from desktop_agent.ollama import OllamaClient, OllamaError


def test_chat_requires_model():
    with pytest.raises(OllamaError, match="Select an Ollama model"):
        OllamaClient("http://127.0.0.1:11434").chat("", [])


def test_list_models_returns_sorted_names(monkeypatch):
    class Response:
        def raise_for_status(self):
            pass
        def json(self):
            return {"models": [{"name": "model-b"}, {"name": "model-a"}]}
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: Response())
    assert OllamaClient("http://127.0.0.1:11434").list_models() == ["model-a", "model-b"]
