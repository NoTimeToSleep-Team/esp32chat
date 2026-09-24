from __future__ import annotations

import sqlite3
from pathlib import Path
from time import time

from app.services.media import MAX_ATTACHMENTS_PER_MESSAGE

ALLOWED_REASONS = ("spam", "abuse", "profanity", "ads", "scam", "other")
MAX_COMMENT_LENGTH = 1000
MAX_WARNS = 3
WARN_BAN_MINUTES = 3 * 24 * 60
AUTO_REPORTER_ID = 0
AUTO_REPORTER_LOGIN = "Авто-модерация"


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
        attachment_ids: tuple[int, ...] = (),
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
        ids = self._normalize_attachment_ids(attachment_ids)

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
            for attachment_id in ids:
                attachment = connection.execute(
                    "SELECT owner_user_id FROM media_attachments WHERE id = ?",
                    (attachment_id,),
                ).fetchone()
                if attachment is None:
                    raise UserReportsError(
                        "attachment_not_found", "Attachment not found", 404
                    )
                if int(attachment["owner_user_id"]) != int(reporter_user_id):
                    raise UserReportsError(
                        "forbidden_attachment",
                        "Cannot attach a file owned by another user",
                        403,
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
            for position, attachment_id in enumerate(ids):
                connection.execute(
                    """
                    INSERT OR IGNORE INTO report_attachments(report_id, attachment_id, position)
                    VALUES (?, ?, ?)
                    """,
                    (report_id, attachment_id, position),
                )
            connection.commit()
        finally:
            connection.close()
        report = self.get(report_id)
        if report is None:
            raise UserReportsError("not_found", "Report was not found after creation", 500)
        return report

    def create_auto(
        self,
        *,
        target_user_id: int,
        target_login: str | None,
        reason: str,
        matched_words: str,
        message_id: int,
        chat_id: int,
        comment: str,
    ) -> dict:
        """File an auto-moderation report (source='auto') into the normal queue."""
        reason = (reason or "").strip().lower()
        if reason not in ALLOWED_REASONS:
            raise UserReportsError(
                "invalid_reason",
                "reason must be one of: " + ", ".join(ALLOWED_REASONS),
                422,
            )
        comment = (comment or "").strip()[:MAX_COMMENT_LENGTH]
        connection = self._connect()
        try:
            try:
                cursor = connection.execute(
                    """
                    INSERT INTO user_reports (
                        reporter_user_id, reporter_login, target_user_id, target_login,
                        reason, comment, status, created_at_ms,
                        source, matched_words, message_id, chat_id
                    ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, 'auto', ?, ?, ?)
                    """,
                    (
                        AUTO_REPORTER_ID,
                        AUTO_REPORTER_LOGIN,
                        int(target_user_id),
                        target_login,
                        reason,
                        comment,
                        _now_ms(),
                        matched_words,
                        int(message_id),
                        int(chat_id),
                    ),
                )
            except sqlite3.OperationalError as exc:
                raise UserReportsError(
                    "auto_columns_missing",
                    "Auto-moderation columns are missing (run migration 0033)",
                    500,
                ) from exc
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

    @staticmethod
    def _normalize_attachment_ids(attachment_ids: tuple[int, ...]) -> tuple[int, ...]:
        ids = tuple(dict.fromkeys(int(value) for value in attachment_ids if int(value) > 0))
        if len(ids) > MAX_ATTACHMENTS_PER_MESSAGE:
            raise UserReportsError(
                "too_many_attachments", "Too many attachments for one report", 422
            )
        return ids

    # ----- warnings -----

    def warn_user(self, *, user_id: int, report_id: int, issued_by_login: str) -> int:
        connection = self._connect()
        try:
            target = connection.execute(
                "SELECT id FROM users WHERE id = ?", (int(user_id),)
            ).fetchone()
            if target is None:
                raise UserReportsError("target_not_found", "User was not found", 404)
            now_ms = _now_ms()
            connection.execute(
                "INSERT INTO user_warnings (user_id, report_id, issued_by_login, created_at_ms) VALUES (?, ?, ?, ?)",
                (int(user_id), int(report_id), issued_by_login, now_ms),
            )
            connection.execute(
                "UPDATE users SET warn_count = COALESCE(warn_count, 0) + 1, updated_at_ms = ? WHERE id = ?",
                (now_ms, int(user_id)),
            )
            row = connection.execute(
                "SELECT warn_count FROM users WHERE id = ?", (int(user_id),)
            ).fetchone()
            connection.commit()
        finally:
            connection.close()
        return int(row["warn_count"]) if row else 0

    def reset_warnings(self, user_id: int) -> None:
        connection = self._connect()
        try:
            connection.execute(
                "UPDATE users SET warn_count = 0, updated_at_ms = ? WHERE id = ?",
                (_now_ms(), int(user_id)),
            )
            connection.commit()
        finally:
            connection.close()

    def warn_count(self, user_id: int) -> int:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT COALESCE(warn_count, 0) AS n FROM users WHERE id = ?", (int(user_id),)
            ).fetchone()
        finally:
            connection.close()
        return int(row["n"]) if row else 0

    def warn_counts_for(self, user_ids: list[int]) -> dict[int, int]:
        ids = [int(uid) for uid in user_ids if uid]
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        connection = self._connect()
        try:
            rows = connection.execute(
                f"SELECT id, COALESCE(warn_count, 0) AS n FROM users WHERE id IN ({placeholders})",
                ids,
            ).fetchall()
        finally:
            connection.close()
        return {int(row["id"]): int(row["n"]) for row in rows}

    def reports_against_counts(self, user_ids: list[int]) -> dict[int, int]:
        ids = [int(uid) for uid in user_ids if uid]
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        connection = self._connect()
        try:
            rows = connection.execute(
                f"SELECT target_user_id, COUNT(*) AS n FROM user_reports WHERE target_user_id IN ({placeholders}) GROUP BY target_user_id",
                ids,
            ).fetchall()
        finally:
            connection.close()
        return {int(row["target_user_id"]): int(row["n"]) for row in rows}

    def my_status(self, user_id: int) -> dict:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT COALESCE(warn_count, 0) AS n FROM users WHERE id = ?", (int(user_id),)
            ).fetchone()
            restriction = connection.execute(
                "SELECT block_reason, blocked_until_ms FROM user_restrictions WHERE user_id = ?",
                (int(user_id),),
            ).fetchone()
        finally:
            connection.close()
        return {
            "warn_count": int(row["n"]) if row else 0,
            "max_warns": MAX_WARNS,
            "block_reason": restriction["block_reason"] if restriction else None,
            "blocked_until_ms": restriction["blocked_until_ms"] if restriction else None,
        }

    def target_messages(self, target_user_id: int, *, limit: int = 10) -> list[dict]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT m.id AS message_id, m.chat_id, m.body_text, m.created_at_ms, c.title AS chat_title
                FROM chat_messages m
                LEFT JOIN chats c ON c.id = m.chat_id
                WHERE m.author_user_id = ? AND COALESCE(c.is_private, 0) = 0
                ORDER BY m.id DESC LIMIT ?
                """,
                (int(target_user_id), int(limit)),
            ).fetchall()
        finally:
            connection.close()
        return [dict(row) for row in rows]
