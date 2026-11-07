"""Local security audit trail with redaction and tamper-evident JSONL records."""

import hashlib
import json
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REDACTED_KEYS = {
    "password", "passwd", "token", "secret", "api_key", "authorization",
    "cookie", "credential", "private_key",
}
_SECRET_RE = re.compile(
    r"(?i)(password|passwd|api[_ -]?key|token|secret|authorization)(\s*[:=]\s*)([^\s,;]+)"
)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if str(key).lower() in _REDACTED_KEYS else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return _SECRET_RE.sub(lambda match: match.group(1) + match.group(2) + "[REDACTED]", value)
    return value


class AuditLog:
    """Writes SQLite records and a hash-chained JSONL stream.

    Hash chaining makes edits/reordering detectable; it is not protection against
    an attacker who can replace the entire log and recompute the chain.
    """

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        self.log_path = Path(self.database_path).with_suffix(".jsonl")
        self._lock = threading.Lock()
        self._last_hash = self._load_last_hash()
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS tool_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
                tool_name TEXT NOT NULL, application TEXT, risk TEXT NOT NULL,
                decision TEXT NOT NULL, outcome TEXT NOT NULL,
                arguments_json TEXT NOT NULL, detail TEXT NOT NULL)""")
            connection.execute("""CREATE TABLE IF NOT EXISTS activity_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
                event_type TEXT NOT NULL, details_json TEXT NOT NULL)""")

    def _load_last_hash(self) -> str:
        if not self.log_path.exists():
            return "0" * 64
        last = "0" * 64
        try:
            with self.log_path.open("r", encoding="utf-8") as stream:
                for line in stream:
                    item = json.loads(line)
                    supplied = item.pop("hash")
                    canonical = json.dumps(item, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
                    expected = hashlib.sha256((last + canonical).encode("utf-8")).hexdigest()
                    if supplied != expected:
                        raise ValueError("Audit log hash-chain verification failed.")
                    last = supplied
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            raise RuntimeError("Existing audit log is invalid; refusing to append.") from exc
        return last

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path, timeout=10)

    def _append_jsonl(self, payload: dict) -> None:
        item = {"previous_hash": self._last_hash, **payload}
        canonical = json.dumps(item, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        digest = hashlib.sha256((self._last_hash + canonical).encode("utf-8")).hexdigest()
        item["hash"] = digest
        with self.log_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")
            stream.flush()
        self._last_hash = digest

    def record_event(self, event_type: str, details: dict | None = None) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        safe = redact(details or {})
        with self._lock:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO activity_events (created_at, event_type, details_json) VALUES (?, ?, ?)",
                    (timestamp, event_type, json.dumps(safe, ensure_ascii=False, default=str)),
                )
            self._append_jsonl({"timestamp": timestamp, "event": event_type, "details": safe})

    def record(self, *, tool_name: str, application: str | None, risk: str,
               decision: str, outcome: str, arguments: dict, detail: str = "") -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        safe_args, safe_detail = redact(arguments), redact(detail[:2000])
        payload = {"timestamp": timestamp, "event": "tool_action", "tool": tool_name,
                   "application": application, "risk": risk, "decision": decision,
                   "outcome": outcome, "arguments": safe_args, "detail": safe_detail}
        with self._lock:
            with self._connect() as connection:
                connection.execute(
                    """INSERT INTO tool_events
                    (created_at, tool_name, application, risk, decision, outcome, arguments_json, detail)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (timestamp, tool_name, application, risk, decision, outcome,
                     json.dumps(safe_args, default=str), safe_detail),
                )
            self._append_jsonl(payload)

    def recent_events(self, limit: int = 100) -> list[dict]:
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT * FROM tool_events ORDER BY id DESC LIMIT ?", (max(1, limit),)
            ).fetchall()
        return [dict(row) for row in rows]

    def verify_jsonl(self) -> bool:
        with self._lock:
            self._last_hash = self._load_last_hash()
        return True
