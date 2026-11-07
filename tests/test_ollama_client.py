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


def test_describe_image_sends_base64_image_to_local_ollama(monkeypatch):
    import base64

    captured = {}

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": "A desktop with an open window."}}

    def fake_post(url, json, timeout):
        captured.update({"url": url, "payload": json, "timeout": timeout})
        return Response()

    monkeypatch.setattr(httpx, "post", fake_post)
    answer = OllamaClient("http://127.0.0.1:11434").describe_image("local-vision", b"png-bytes")
    assert answer == "A desktop with an open window."
    assert captured["url"].endswith("/api/chat")
    message = captured["payload"]["messages"][1]
    assert message["images"] == [base64.b64encode(b"png-bytes").decode("ascii")]
    assert "untrusted content" in captured["payload"]["messages"][0]["content"]


def test_describe_image_rejects_oversized_input():
    with pytest.raises(OllamaError, match="4 MiB"):
        OllamaClient("http://127.0.0.1:11434").describe_image("vision", b"x" * (4 * 1024 * 1024 + 1))

def test_describe_image_refuses_non_loopback_ollama():
    with pytest.raises(OllamaError, match="loopback"):
        OllamaClient("http://192.168.1.20:11434").describe_image("vision", b"image")
