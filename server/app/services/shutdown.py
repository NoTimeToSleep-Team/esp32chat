from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from time import time

from app.models import (
    RuntimeState,
    ShutdownRunKind,
    ShutdownRunRecord,
    ShutdownRunStatus,
    UserRole,
    UserStatus,
)


def _now_ms() -> int:
    return int(time() * 1000)


@dataclass(frozen=True)
class ShutdownError(RuntimeError):
    code: str
    message: str
    status_code: int

    def __str__(self) -> str:
        return self.message


class ShutdownService:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)

    def get_runtime_state(self) -> RuntimeState:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT degraded_mode, reason, updated_by_user_id, updated_at_ms
                FROM ops_runtime_state
                WHERE id = 1
                """,
            ).fetchone()
            if row is None:
                return RuntimeState(
                    degraded_mode=False,
                    reason=None,
                    updated_by_user_id=None,
                    updated_at_ms=0,
                )
            return self._row_to_runtime_state(row)

    def set_degraded_mode(
        self,
        *,
        actor_user_id: int,
        enabled: bool,
        reason: str | None = None,
    ) -> RuntimeState:
        normalized_reason = (reason or "").strip() or None
        now_ms = _now_ms()

        with self._connect() as connection:
            self._require_active_admin(connection, actor_user_id)
            connection.execute(
                """
                INSERT INTO ops_runtime_state(id, degraded_mode, reason, updated_by_user_id, updated_at_ms)
                VALUES (1, ?, ?, ?, ?)
                ON CONFLICT(id)
                DO UPDATE SET
                    degraded_mode = excluded.degraded_mode,
                    reason = excluded.reason,
                    updated_by_user_id = excluded.updated_by_user_id,
                    updated_at_ms = excluded.updated_at_ms
                """,
                (1 if enabled else 0, normalized_reason, actor_user_id, now_ms),
            )

            row = connection.execute(
                """
                SELECT degraded_mode, reason, updated_by_user_id, updated_at_ms
                FROM ops_runtime_state
                WHERE id = 1
                """,
            ).fetchone()
            if row is None:
                raise ShutdownError("runtime_state_update_failed", "Failed to update runtime state", 500)
            return self._row_to_runtime_state(row)

    def run_shutdown_dry(self, *, actor_user_id: int, reason: str | None = None) -> ShutdownRunRecord:
        normalized_reason = (reason or "").strip() or None
        started_at_ms = _now_ms()

        steps = [
            {
                "step": "freeze_authentication",
                "status": "simulated",
                "note": "Would disable new login sessions",
            },
            {
                "step": "switch_degraded_mode",
                "status": "simulated",
                "note": "Would enable degraded mode for active clients",
            },
            {
                "step": "flush_audit_and_runtime_logs",
                "status": "simulated",
                "note": "Would flush buffered logs to disk",
            },
            {
                "step": "final_backup_snapshot",
                "status": "simulated",
                "note": "Would trigger last DB backup before stop",
            },
            {
                "step": "stop_service",
                "status": "simulated",
                "note": "Would hand over to systemd stop sequence",
            },
        ]
        steps_json = json.dumps(steps, ensure_ascii=True, separators=(",", ":"))
        finished_at_ms = _now_ms()

        with self._connect() as connection:
            self._require_active_admin(connection, actor_user_id)
            cursor = connection.execute(
                """
                INSERT INTO ops_shutdown_runs(
                    run_kind,
                    requested_by_user_id,
                    reason,
                    status,
                    started_at_ms,
                    finished_at_ms,
                    steps_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ShutdownRunKind.DRY_RUN.value,
                    actor_user_id,
                    normalized_reason,
                    ShutdownRunStatus.COMPLETED.value,
                    started_at_ms,
                    finished_at_ms,
                    steps_json,
                ),
            )

            row = connection.execute(
                "SELECT * FROM ops_shutdown_runs WHERE id = ?",
                (int(cursor.lastrowid),),
            ).fetchone()
            if row is None:
                raise ShutdownError("shutdown_run_failed", "Failed to store shutdown dry-run", 500)
            return self._row_to_shutdown_run(row)

    def list_shutdown_runs(
        self,
        *,
        actor_user_id: int,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ShutdownRunRecord]:
        safe_limit = min(max(limit, 1), 500)
        safe_offset = max(offset, 0)

        with self._connect() as connection:
            self._require_active_admin(connection, actor_user_id)
            rows = connection.execute(
                """
                SELECT *
                FROM ops_shutdown_runs
                ORDER BY started_at_ms DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (safe_limit, safe_offset),
            ).fetchall()
            return [self._row_to_shutdown_run(row) for row in rows]

    @staticmethod
    def _row_to_runtime_state(row: sqlite3.Row) -> RuntimeState:
        return RuntimeState(
            degraded_mode=bool(int(row["degraded_mode"])),
            reason=str(row["reason"]) if row["reason"] is not None else None,
            updated_by_user_id=int(row["updated_by_user_id"])
            if row["updated_by_user_id"] is not None
            else None,
            updated_at_ms=int(row["updated_at_ms"]),
        )

    @staticmethod
    def _row_to_shutdown_run(row: sqlite3.Row) -> ShutdownRunRecord:
        return ShutdownRunRecord(
            run_id=int(row["id"]),
            run_kind=ShutdownRunKind(str(row["run_kind"])),
            requested_by_user_id=int(row["requested_by_user_id"])
            if row["requested_by_user_id"] is not None
            else None,
            reason=str(row["reason"]) if row["reason"] is not None else None,
            status=ShutdownRunStatus(str(row["status"])),
            started_at_ms=int(row["started_at_ms"]),
            finished_at_ms=int(row["finished_at_ms"]) if row["finished_at_ms"] is not None else None,
            steps_json=str(row["steps_json"]),
        )

    @staticmethod
    def _require_active_admin(connection: sqlite3.Connection, actor_user_id: int) -> None:
        row = connection.execute(
            "SELECT role, status FROM users WHERE id = ?",
            (actor_user_id,),
        ).fetchone()
        if row is None:
            raise ShutdownError("actor_not_found", "Actor user was not found", 404)

        role = str(row["role"])
        status = str(row["status"])
        if role != UserRole.ADMIN.value:
            raise ShutdownError("admin_only", "Admin role is required", 403)
        if status != UserStatus.ACTIVE.value:
            raise ShutdownError("actor_inactive", "Admin account is not active", 403)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection
