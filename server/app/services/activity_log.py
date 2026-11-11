from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from app.db.connection import connect_sqlite


def _now_ms() -> int:
    return int(time.time() * 1000)


class ActivityLogService:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)

    def _init_table(self, connection: sqlite3.Connection) -> None:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event TEXT NOT NULL,
                user_id INTEGER,
                user_login TEXT,
                details TEXT,
                created_at_ms INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_activity_time ON activity_log(created_at_ms);
        """)

    def log(self, event: str, user_id: int | None = None, user_login: str | None = None, details: str | None = None) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO activity_log (event, user_id, user_login, details, created_at_ms) VALUES (?, ?, ?, ?, ?)",
                    (event, user_id, user_login, details, _now_ms()),
                )
        except Exception:
            pass

    def get_logs(self, limit: int = 100, offset: int = 0) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM activity_log ORDER BY created_at_ms DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            return [{"id": r["id"], "event": r["event"], "user_id": r["user_id"],
                     "user_login": r["user_login"], "details": r["details"],
                     "time": r["created_at_ms"]} for r in rows]

    def stats(self) -> dict:
        one_month_ago = _now_ms() - 30 * 86400 * 1000
        with self._connect() as conn:
            msgs = conn.execute(
                "SELECT COUNT(*) FROM chat_messages WHERE created_at_ms >= ?", (one_month_ago,)
            ).fetchone()[0]
            users = conn.execute(
                "SELECT COUNT(*) FROM users WHERE created_at_ms >= ?", (one_month_ago,)
            ).fetchone()[0]
            total_logs = conn.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0]
            total_ws = 0
            try:
                total_ws = connection.execute("SELECT COUNT(DISTINCT user_id) FROM sessions WHERE revoked_at_ms IS NULL").fetchone()[0]
            except:
                pass
            return {"messages_30d": msgs, "users_30d": users, "total_events": total_logs, "active_sessions": total_ws}

    def _connect(self) -> sqlite3.Connection:
        conn = connect_sqlite(self._db_path)
        self._init_table(conn)
        return conn
