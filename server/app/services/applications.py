from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from time import time

from app.models import AccessMode, ApplicationDraft, ApplicationRecord, ApplicationStatus


def _now_ms() -> int:
    return int(time() * 1000)


@dataclass(frozen=True)
class ApplicationError(RuntimeError):
    code: str
    message: str
    status_code: int

    def __str__(self) -> str:
        return self.message


class ApplicationService:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)

    def submit(self, draft: ApplicationDraft) -> ApplicationRecord:
        with self._connect() as connection:
            access_mode = self._read_access_mode(connection)
            if access_mode != AccessMode.CLOSED:
                raise ApplicationError(
                    code="applications_disabled",
                    message="Application flow is available only in closed mode",
                    status_code=409,
                )

            now_ms = _now_ms()
            cursor = connection.execute(
                """
                INSERT INTO applications(
                    first_name,
                    last_name,
                    phone,
                    email,
                    class_group,
                    is_school_member,
                    status,
                    review_note,
                    reviewed_by_user_id,
                    created_at_ms,
                    updated_at_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)
                """,
                (
                    draft.first_name.strip(),
                    draft.last_name.strip(),
                    draft.phone.strip(),
                    draft.email.strip().lower(),
                    draft.class_group.strip(),
                    1 if draft.is_school_member else 0,
                    ApplicationStatus.PENDING.value,
                    now_ms,
                    now_ms,
                ),
            )
            application_id = int(cursor.lastrowid)

            row = connection.execute(
                "SELECT * FROM applications WHERE id = ?",
                (application_id,),
            ).fetchone()
            if row is None:
                raise ApplicationError("create_failed", "Application was not created", 500)

            return self._row_to_record(row)

    def list_queue(
        self,
        *,
        status: ApplicationStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ApplicationRecord]:
        safe_limit = min(max(limit, 1), 500)
        safe_offset = max(offset, 0)

        with self._connect() as connection:
            if status is None:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM applications
                    ORDER BY created_at_ms ASC
                    LIMIT ? OFFSET ?
                    """,
                    (safe_limit, safe_offset),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM applications
                    WHERE status = ?
                    ORDER BY created_at_ms ASC
                    LIMIT ? OFFSET ?
                    """,
                    (status.value, safe_limit, safe_offset),
                ).fetchall()

            return [self._row_to_record(row) for row in rows]

    def set_status(
        self,
        *,
        application_id: int,
        new_status: ApplicationStatus,
        reviewed_by_user_id: int,
        review_note: str | None = None,
    ) -> ApplicationRecord:
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT id FROM applications WHERE id = ?",
                (application_id,),
            ).fetchone()
            if existing is None:
                raise ApplicationError("not_found", "Application was not found", 404)

            now_ms = _now_ms()
            connection.execute(
                """
                UPDATE applications
                SET status = ?,
                    review_note = ?,
                    reviewed_by_user_id = ?,
                    updated_at_ms = ?
                WHERE id = ?
                """,
                (
                    new_status.value,
                    (review_note or "").strip() or None,
                    reviewed_by_user_id,
                    now_ms,
                    application_id,
                ),
            )

            row = connection.execute(
                "SELECT * FROM applications WHERE id = ?",
                (application_id,),
            ).fetchone()
            if row is None:
                raise ApplicationError("not_found", "Application was not found", 404)

            return self._row_to_record(row)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _read_access_mode(connection: sqlite3.Connection) -> AccessMode:
        row = connection.execute(
            "SELECT access_mode FROM mode_state WHERE id = 1"
        ).fetchone()
        if row is None:
            return AccessMode.CLOSED
        try:
            return AccessMode(str(row["access_mode"]))
        except ValueError:
            return AccessMode.CLOSED

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> ApplicationRecord:
        return ApplicationRecord(
            application_id=int(row["id"]),
            first_name=str(row["first_name"]),
            last_name=str(row["last_name"]),
            phone=str(row["phone"]),
            email=str(row["email"]),
            class_group=str(row["class_group"]),
            is_school_member=bool(int(row["is_school_member"])),
            status=ApplicationStatus(str(row["status"])),
            review_note=str(row["review_note"]) if row["review_note"] is not None else None,
            reviewed_by_user_id=int(row["reviewed_by_user_id"])
            if row["reviewed_by_user_id"] is not None
            else None,
            created_at_ms=int(row["created_at_ms"]),
            updated_at_ms=int(row["updated_at_ms"]),
        )
