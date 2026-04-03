from __future__ import annotations

import json
import secrets
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from time import time
from typing import Mapping

from app.models import IncidentLevel, IncidentRecord, IncidentStatus, UserRole, UserStatus


def _now_ms() -> int:
    return int(time() * 1000)


@dataclass(frozen=True)
class IncidentError(RuntimeError):
    code: str
    message: str
    status_code: int

    def __str__(self) -> str:
        return self.message


class IncidentService:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)

    def create_incident(
        self,
        *,
        actor_user_id: int,
        level: IncidentLevel,
        title: str,
        details: Mapping[str, object] | None = None,
        source: str | None = None,
    ) -> IncidentRecord:
        normalized_title = title.strip()
        if not normalized_title:
            raise IncidentError("invalid_title", "Incident title must not be empty", 422)

        details_json = json.dumps(details or {}, ensure_ascii=True, separators=(",", ":"))
        normalized_source = (source or "").strip() or None
        now_ms = _now_ms()
        incident_key = self._generate_incident_key(now_ms)

        with self._connect() as connection:
            self._require_active_admin(connection, actor_user_id)
            cursor = connection.execute(
                """
                INSERT INTO ops_incidents(
                    incident_key,
                    level,
                    title,
                    details_json,
                    source,
                    status,
                    created_at_ms,
                    updated_at_ms,
                    resolved_at_ms,
                    created_by_user_id,
                    resolved_by_user_id,
                    resolution_note
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, NULL, NULL)
                """,
                (
                    incident_key,
                    level.value,
                    normalized_title,
                    details_json,
                    normalized_source,
                    IncidentStatus.OPEN.value,
                    now_ms,
                    now_ms,
                    actor_user_id,
                ),
            )

            row = connection.execute(
                "SELECT * FROM ops_incidents WHERE id = ?",
                (int(cursor.lastrowid),),
            ).fetchone()
            if row is None:
                raise IncidentError("incident_create_failed", "Failed to create incident", 500)
            return self._row_to_incident(row)

    def list_incidents(
        self,
        *,
        actor_user_id: int,
        status: IncidentStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[IncidentRecord]:
        safe_limit = min(max(limit, 1), 500)
        safe_offset = max(offset, 0)

        with self._connect() as connection:
            self._require_active_admin(connection, actor_user_id)
            if status is None:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM ops_incidents
                    ORDER BY created_at_ms DESC, id DESC
                    LIMIT ? OFFSET ?
                    """,
                    (safe_limit, safe_offset),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM ops_incidents
                    WHERE status = ?
                    ORDER BY created_at_ms DESC, id DESC
                    LIMIT ? OFFSET ?
                    """,
                    (status.value, safe_limit, safe_offset),
                ).fetchall()
            return [self._row_to_incident(row) for row in rows]

    def resolve_incident(
        self,
        *,
        actor_user_id: int,
        incident_id: int,
        resolution_note: str | None = None,
    ) -> IncidentRecord:
        normalized_note = (resolution_note or "").strip() or None
        now_ms = _now_ms()

        with self._connect() as connection:
            self._require_active_admin(connection, actor_user_id)

            updated = connection.execute(
                """
                UPDATE ops_incidents
                SET status = ?,
                    updated_at_ms = ?,
                    resolved_at_ms = ?,
                    resolved_by_user_id = ?,
                    resolution_note = ?
                WHERE id = ?
                """,
                (
                    IncidentStatus.RESOLVED.value,
                    now_ms,
                    now_ms,
                    actor_user_id,
                    normalized_note,
                    incident_id,
                ),
            ).rowcount
            if updated <= 0:
                raise IncidentError("incident_not_found", "Incident was not found", 404)

            row = connection.execute(
                "SELECT * FROM ops_incidents WHERE id = ?",
                (incident_id,),
            ).fetchone()
            if row is None:
                raise IncidentError("incident_not_found", "Incident was not found", 404)
            return self._row_to_incident(row)

    @staticmethod
    def _generate_incident_key(now_ms: int) -> str:
        token = secrets.token_hex(3)
        return f"INC-{now_ms}-{token}"

    @staticmethod
    def _row_to_incident(row: sqlite3.Row) -> IncidentRecord:
        return IncidentRecord(
            incident_id=int(row["id"]),
            incident_key=str(row["incident_key"]),
            level=IncidentLevel(str(row["level"])),
            title=str(row["title"]),
            details_json=str(row["details_json"]),
            source=str(row["source"]) if row["source"] is not None else None,
            status=IncidentStatus(str(row["status"])),
            created_at_ms=int(row["created_at_ms"]),
            updated_at_ms=int(row["updated_at_ms"]),
            resolved_at_ms=int(row["resolved_at_ms"]) if row["resolved_at_ms"] is not None else None,
            created_by_user_id=int(row["created_by_user_id"])
            if row["created_by_user_id"] is not None
            else None,
            resolved_by_user_id=int(row["resolved_by_user_id"])
            if row["resolved_by_user_id"] is not None
            else None,
            resolution_note=str(row["resolution_note"]) if row["resolution_note"] is not None else None,
        )

    @staticmethod
    def _require_active_admin(connection: sqlite3.Connection, actor_user_id: int) -> None:
        row = connection.execute(
            "SELECT role, status FROM users WHERE id = ?",
            (actor_user_id,),
        ).fetchone()
        if row is None:
            raise IncidentError("actor_not_found", "Actor user was not found", 404)

        role = str(row["role"])
        status = str(row["status"])
        if role != UserRole.ADMIN.value:
            raise IncidentError("admin_only", "Admin role is required", 403)
        if status != UserStatus.ACTIVE.value:
            raise IncidentError("actor_inactive", "Admin account is not active", 403)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection
