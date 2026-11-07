import pytest

from desktop_agent.config import Settings


def test_environment_overrides(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/")
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", "45")
    settings = Settings.from_environment()
    assert settings.ollama_base_url == "http://localhost:11434"
    assert settings.ollama_timeout_seconds == 45


def test_rejects_unsafe_http_host(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://example.com:11434")
    with pytest.raises(ValueError, match="Ollama URL"):
        Settings.from_environment()


def test_rejects_nonpositive_timeout(monkeypatch):
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", "0")
    with pytest.raises(ValueError, match="greater than zero"):
        Settings.from_environment()
