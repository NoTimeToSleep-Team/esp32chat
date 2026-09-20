from __future__ import annotations

import sqlite3
from pathlib import Path
from time import time

ALLOWED_REASONS = ("spam", "abuse", "profanity", "ads", "scam", "other")
MAX_COMMENT_LENGTH = 1000


def _now_ms() -> int:
    return int(time() * 1000)


class UserReportsError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def __str__(self) -> str:
        return self.message


class UserReportsService:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def create(
        self,
        *,
        reporter_user_id: int,
        reporter_login: str,
        target_user_id: int,
        reason: str,
        comment: str,
    ) -> dict:
        reason = (reason or "").strip().lower()
        if reason not in ALLOWED_REASONS:
            raise UserReportsError(
                "invalid_reason",
                "reason must be one of: " + ", ".join(ALLOWED_REASONS),
                422,
            )
        comment = (comment or "").strip()[:MAX_COMMENT_LENGTH]
        target_user_id = int(target_user_id)
        if target_user_id == int(reporter_user_id):
            raise UserReportsError("self_report", "You cannot report yourself", 422)

        connection = self._connect()
        try:
            target = connection.execute(
                "SELECT id, login, display_name FROM users WHERE id = ?",
                (target_user_id,),
            ).fetchone()
            if target is None:
                raise UserReportsError(
                    "target_not_found", "The user you are reporting was not found", 404
                )
            duplicate = connection.execute(
                "SELECT id FROM user_reports "
                "WHERE reporter_user_id = ? AND target_user_id = ? AND status = 'pending'",
                (int(reporter_user_id), target_user_id),
            ).fetchone()
            if duplicate is not None:
                raise UserReportsError(
                    "already_reported",
                    "You have already reported this user; the report is under review",
                    409,
                )
            cursor = connection.execute(
                """
                INSERT INTO user_reports (
                    reporter_user_id, reporter_login, target_user_id, target_login,
                    reason, comment, status, created_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    int(reporter_user_id),
                    reporter_login,
                    target_user_id,
                    target["login"],
                    reason,
                    comment,
                    _now_ms(),
                ),
            )
            report_id = int(cursor.lastrowid)
            connection.commit()
        finally:
            connection.close()
        report = self.get(report_id)
        if report is None:
            raise UserReportsError("not_found", "Report was not found after creation", 500)
        return report

    def get(self, report_id: int) -> dict | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM user_reports WHERE id = ?", (int(report_id),)
            ).fetchone()
        finally:
            connection.close()
        return dict(row) if row else None

    def list_reports(self, *, status: str | None = None, limit: int = 100) -> list[dict]:
        connection = self._connect()
        try:
            query = "SELECT * FROM user_reports"
            params: tuple = ()
            if status:
                query += " WHERE status = ?"
                params += (status,)
            query += " ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, created_at_ms DESC LIMIT ?"
            params += (int(limit),)
            rows = connection.execute(query, params).fetchall()
        finally:
            connection.close()
        return [dict(row) for row in rows]

    def count_pending(self) -> int:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT COUNT(*) AS n FROM user_reports WHERE status = 'pending'"
            ).fetchone()
        finally:
            connection.close()
        return int(row["n"]) if row else 0

    def resolve(self, report_id: int, action: str, admin_login: str) -> dict:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM user_reports WHERE id = ?", (int(report_id),)
            ).fetchone()
            if row is None:
                raise UserReportsError("report_not_found", "Report not found", 404)
            if row["status"] != "pending":
                raise UserReportsError(
                    "already_resolved", "Report has already been resolved", 409
                )
            connection.execute(
                "UPDATE user_reports SET status = 'resolved', action = ?, resolved_by = ?, resolved_at_ms = ? WHERE id = ?",
                (action, admin_login, _now_ms(), int(report_id)),
            )
            connection.commit()
        finally:
            connection.close()
        resolved = self.get(report_id)
        if resolved is None:
            raise UserReportsError("report_not_found", "Report not found", 404)
        return resolved
