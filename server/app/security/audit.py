from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from time import time
from typing import Mapping


def _now_ms() -> int:
    return int(time() * 1000)


class SecurityAuditService:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)

    def log_event(
        self,
        event_type: str,
        *,
        actor_kind: str | None = None,
        actor_id: str | None = None,
        details: Mapping[str, object] | None = None,
    ) -> None:
        payload = json.dumps(details or {}, ensure_ascii=True, separators=(",", ":"))
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO audit_log(event_type, actor_kind, actor_id, details_json, created_at_ms)
                VALUES (?, ?, ?, ?, ?)
                """,
                (event_type, actor_kind, actor_id, payload, _now_ms()),
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection
