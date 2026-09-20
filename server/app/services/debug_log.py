from __future__ import annotations

import sqlite3
from pathlib import Path
from time import time


class DebugLogService:
    """Stores debug traces (client stages, server receipts, UI toasts)."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)

    def log(
        self,
        *,
        stage: str,
        trace_id: str | None = None,
        action: str | None = None,
        method: str | None = None,
        status: int | None = None,
        ok: bool | None = None,
        stages_done: int | None = None,
        error: str | None = None,
        details: str | None = None,
        user_login: str | None = None,
        ip: str | None = None,
        t1_ms: int | None = None,
        t2_ms: int | None = None,
        t3_ms: int | None = None,
    ) -> int | None:
        try:
            connection = sqlite3.connect(self._db_path, timeout=5)
            connection.execute("PRAGMA busy_timeout = 3000")
            cursor = connection.execute(
                """
                INSERT INTO debug_events(
                    created_at_ms, stage, trace_id, action, method, status, ok,
                    stages_done, error, details, user_login, ip, t1_ms, t2_ms, t3_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(time() * 1000),
                    stage,
                    trace_id,
                    action,
                    method,
                    status,
                    None if ok is None else (1 if ok else 0),
                    stages_done,
                    error,
                    details,
                    user_login,
                    ip,
                    t1_ms,
                    t2_ms,
                    t3_ms,
                ),
            )
            connection.commit()
            row_id = cursor.lastrowid
            connection.close()
            return int(row_id) if row_id is not None else None
        except sqlite3.Error:
            return None

    def list_events(self, *, limit: int = 200, trace_id: str | None = None) -> list[dict]:
        try:
            connection = sqlite3.connect(self._db_path, timeout=5)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA busy_timeout = 3000")
            if trace_id:
                rows = connection.execute(
                    "SELECT * FROM debug_events WHERE trace_id = ? ORDER BY id DESC LIMIT ?",
                    (trace_id, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM debug_events ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            connection.close()
            return [dict(row) for row in rows]
        except sqlite3.Error:
            return []
