"""Environment-backed application settings."""

from dataclasses import dataclass
import os
from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_timeout_seconds: float = 120.0

    @classmethod
    def from_environment(cls) -> "Settings":
        load_dotenv()
        base_url = os.getenv("OLLAMA_BASE_URL", cls.ollama_base_url).rstrip("/")
        raw_timeout = os.getenv("OLLAMA_TIMEOUT_SECONDS", str(cls.ollama_timeout_seconds))
        try:
            timeout = float(raw_timeout)
        except ValueError as exc:
            raise ValueError("OLLAMA_TIMEOUT_SECONDS must be numeric") from exc
        if timeout <= 0:
            raise ValueError("OLLAMA_TIMEOUT_SECONDS must be greater than zero")
        if not base_url.startswith(("http://127.0.0.1", "http://localhost", "https://")):
            raise ValueError("Ollama URL must use localhost/127.0.0.1 or HTTPS")
        return cls(base_url, timeout)
