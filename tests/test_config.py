from desktop_agent.config import Settings


def test_default_settings_use_local_ollama():
    settings = Settings()
    assert settings.ollama_base_url == "http://127.0.0.1:11434"
    assert settings.ollama_timeout_seconds > 0
