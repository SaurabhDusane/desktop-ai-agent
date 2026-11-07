"""Append-only local audit trail with basic sensitive-field redaction."""

import json
import sqlite3
import threading
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REDACTED_KEYS = {"password", "passwd", "token", "secret", "api_key", "authorization", "cookie"}
_SECRET_RE = re.compile(r"(?i)(password|passwd|api[_ -]?key|token|secret)(\\s*[:=]\\s*)([^\\s,;]+)")


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if key.lower() in _REDACTED_KEYS else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return _SECRET_RE.sub(lambda m: m.group(1) + m.group(2) + "[REDACTED]", value)
    return value


class AuditLog:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        self.log_path = Path(self.database_path).with_suffix(".jsonl")
        self._lock = threading.Lock()
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS tool_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    application TEXT,
                    risk TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    arguments_json TEXT NOT NULL,
                    detail TEXT NOT NULL
                )"""
            )
            connection.execute("""CREATE TABLE IF NOT EXISTS activity_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
                event_type TEXT NOT NULL, details_json TEXT NOT NULL
            )""")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)

    def record_event(self, event_type: str, details: dict | None = None) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        safe = redact(details or {})
        payload = {"timestamp": timestamp, "event": event_type, "details": safe}
        with self._lock:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO activity_events (created_at, event_type, details_json) VALUES (?, ?, ?)",
                    (timestamp, event_type, json.dumps(safe, ensure_ascii=False, default=str)),
                )
            with self.log_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(payload, ensure_ascii=False, default=str) + "\\n")
                stream.flush()

    def record(
        self, *, tool_name: str, application: str | None, risk: str,
        decision: str, outcome: str, arguments: dict, detail: str = "",
    ) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """INSERT INTO tool_events
                (created_at, tool_name, application, risk, decision, outcome, arguments_json, detail)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (datetime.now(timezone.utc).isoformat(), tool_name, application, risk,
                 decision, outcome, json.dumps(redact(arguments), default=str), detail[:2000]),
            )

    def recent_events(self, limit: int = 100) -> list[dict]:
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT * FROM tool_events ORDER BY id DESC LIMIT ?", (max(1, limit),)
            ).fetchall()
        return [dict(row) for row in rows]
