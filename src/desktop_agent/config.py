"""Environment-backed application settings."""

from dataclasses import dataclass
import os
from urllib.parse import urlparse

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_timeout_seconds: float = 120.0

    @classmethod
    def from_environment(cls) -> "Settings":
        load_dotenv()
        base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        raw_timeout = os.getenv("OLLAMA_TIMEOUT_SECONDS", "120")
        try:
            timeout = float(raw_timeout)
        except ValueError as exc:
            raise ValueError("OLLAMA_TIMEOUT_SECONDS must be numeric") from exc
        if timeout <= 0:
            raise ValueError("OLLAMA_TIMEOUT_SECONDS must be greater than zero")

        parsed = urlparse(base_url)
        is_local = parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}
        is_secure_remote = parsed.scheme == "https" and bool(parsed.hostname)
        if not (is_local or is_secure_remote):
            raise ValueError("Ollama URL must use localhost/127.0.0.1 over HTTP or HTTPS")
        return cls(base_url, timeout)
