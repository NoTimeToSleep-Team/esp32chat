from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from time import time

from app.models import (
    SupportMessage,
    SupportMessageDraft,
    SupportTicket,
    SupportTicketDraft,
    SupportTicketStatus,
    UserRole,
    UserStatus,
)


def _now_ms() -> int:
    return int(time() * 1000)


@dataclass(frozen=True)
class SupportError(RuntimeError):
    code: str
    message: str
    status_code: int

    def __str__(self) -> str:
        return self.message


class SupportService:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)

    def create_ticket(self, *, requester_user_id: int, draft: SupportTicketDraft) -> SupportTicket:
        with self._connect() as connection:
            requester = self._require_support_user(connection, requester_user_id)

            now_ms = _now_ms()
            ticket_cursor = connection.execute(
                """
                INSERT INTO support_tickets(
                    user_id,
                    title,
                    status,
                    created_at_ms,
                    updated_at_ms,
                    last_message_at_ms
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    requester_user_id,
                    draft.title.strip(),
                    SupportTicketStatus.OPEN.value,
                    now_ms,
                    now_ms,
                    now_ms,
                ),
            )
            ticket_id = self._lastrowid(ticket_cursor)

            connection.execute(
                """
                INSERT INTO support_messages(
                    ticket_id,
                    author_user_id,
                    body_text,
                    created_at_ms
                )
                VALUES (?, ?, ?, ?)
                """,
                (ticket_id, requester_user_id, draft.body_text.strip(), now_ms),
            )

            if str(requester["role"]) == UserRole.ADMIN.value:
                connection.execute(
                    "UPDATE support_tickets SET status = ? WHERE id = ?",
                    (SupportTicketStatus.IN_PROGRESS.value, ticket_id),
                )

            row = connection.execute(
                "SELECT * FROM support_tickets WHERE id = ?",
                (ticket_id,),
            ).fetchone()
            if row is None:
                raise SupportError("ticket_create_failed", "Failed to create support ticket", 500)
            return self._row_to_ticket(row)

    def list_tickets(
        self,
        *,
        requester_user_id: int,
        status: SupportTicketStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SupportTicket]:
        safe_limit = min(max(limit, 1), 300)
        safe_offset = max(offset, 0)

        with self._connect() as connection:
            requester = self._require_support_user(connection, requester_user_id)
            is_admin = str(requester["role"]) == UserRole.ADMIN.value

            if is_admin and status is None:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM support_tickets
                    ORDER BY updated_at_ms DESC, id DESC
                    LIMIT ? OFFSET ?
                    """,
                    (safe_limit, safe_offset),
                ).fetchall()
            elif is_admin and status is not None:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM support_tickets
                    WHERE status = ?
                    ORDER BY updated_at_ms DESC, id DESC
                    LIMIT ? OFFSET ?
                    """,
                    (status.value, safe_limit, safe_offset),
                ).fetchall()
            elif status is None:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM support_tickets
                    WHERE user_id = ?
                    ORDER BY updated_at_ms DESC, id DESC
                    LIMIT ? OFFSET ?
                    """,
                    (requester_user_id, safe_limit, safe_offset),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM support_tickets
                    WHERE user_id = ? AND status = ?
                    ORDER BY updated_at_ms DESC, id DESC
                    LIMIT ? OFFSET ?
                    """,
                    (requester_user_id, status.value, safe_limit, safe_offset),
                ).fetchall()

            return [self._row_to_ticket(row) for row in rows]

    def list_messages(
        self,
        *,
        ticket_id: int,
        requester_user_id: int,
        limit: int = 200,
        offset: int = 0,
    ) -> list[SupportMessage]:
        safe_limit = min(max(limit, 1), 500)
        safe_offset = max(offset, 0)

        with self._connect() as connection:
            requester = self._require_support_user(connection, requester_user_id)
            ticket = self._require_ticket(connection, ticket_id)

            if not self._can_access_ticket(
                requester_user_id=requester_user_id,
                requester_role=str(requester["role"]),
                ticket_user_id=self._row_int(ticket, "user_id"),
            ):
                raise SupportError("forbidden", "User has no access to this support ticket", 403)

            rows = connection.execute(
                """
                SELECT *
                FROM support_messages
                WHERE ticket_id = ?
                ORDER BY created_at_ms ASC, id ASC
                LIMIT ? OFFSET ?
                """,
                (ticket_id, safe_limit, safe_offset),
            ).fetchall()
            return [self._row_to_message(row) for row in rows]

    def send_message(
        self,
        *,
        ticket_id: int,
        author_user_id: int,
        draft: SupportMessageDraft,
    ) -> SupportMessage:
        with self._connect() as connection:
            author = self._require_support_user(connection, author_user_id)
            ticket = self._require_ticket(connection, ticket_id)

            if not self._can_access_ticket(
                requester_user_id=author_user_id,
                requester_role=str(author["role"]),
                ticket_user_id=self._row_int(ticket, "user_id"),
            ):
                raise SupportError("forbidden", "User has no access to this support ticket", 403)

            now_ms = _now_ms()
            cursor = connection.execute(
                """
                INSERT INTO support_messages(
                    ticket_id,
                    author_user_id,
                    body_text,
                    created_at_ms
                )
                VALUES (?, ?, ?, ?)
                """,
                (ticket_id, author_user_id, draft.body_text.strip(), now_ms),
            )
            message_id = self._lastrowid(cursor)

            status_value = str(ticket["status"])
            if (
                str(author["role"]) == UserRole.ADMIN.value
                and status_value == SupportTicketStatus.OPEN.value
            ):
                status_value = SupportTicketStatus.IN_PROGRESS.value

            connection.execute(
                """
                UPDATE support_tickets
                SET updated_at_ms = ?,
                    last_message_at_ms = ?,
                    status = ?
                WHERE id = ?
                """,
                (now_ms, now_ms, status_value, ticket_id),
            )

            row = connection.execute(
                "SELECT * FROM support_messages WHERE id = ?",
                (message_id,),
            ).fetchone()
            if row is None:
                raise SupportError("message_create_failed", "Failed to save support message", 500)
            return self._row_to_message(row)

    def set_ticket_status(
        self,
        *,
        ticket_id: int,
        actor_user_id: int,
        status: SupportTicketStatus,
    ) -> SupportTicket:
        with self._connect() as connection:
            actor = self._require_support_user(connection, actor_user_id)
            if str(actor["role"]) != UserRole.ADMIN.value:
                raise SupportError("admin_only", "Only admin can change support status", 403)

            self._require_ticket(connection, ticket_id)

            now_ms = _now_ms()
            connection.execute(
                """
                UPDATE support_tickets
                SET status = ?,
                    updated_at_ms = ?
                WHERE id = ?
                """,
                (status.value, now_ms, ticket_id),
            )

            row = connection.execute(
                "SELECT * FROM support_tickets WHERE id = ?",
                (ticket_id,),
            ).fetchone()
            if row is None:
                raise SupportError("ticket_not_found", "Support ticket was not found", 404)
            return self._row_to_ticket(row)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _require_support_user(connection: sqlite3.Connection, user_id: int) -> sqlite3.Row:
        row = connection.execute(
            "SELECT id, role, status FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            raise SupportError("user_not_found", "User was not found", 404)
        if str(row["status"]) != UserStatus.ACTIVE.value:
            raise SupportError("inactive_user", "User account is not active", 403)
        if str(row["role"]) == UserRole.GUEST.value:
            raise SupportError("guest_not_allowed", "Guest account cannot use support", 403)
        return row

    @staticmethod
    def _require_ticket(connection: sqlite3.Connection, ticket_id: int) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM support_tickets WHERE id = ?",
            (ticket_id,),
        ).fetchone()
        if row is None:
            raise SupportError("ticket_not_found", "Support ticket was not found", 404)
        return row

    @staticmethod
    def _can_access_ticket(
        *,
        requester_user_id: int,
        requester_role: str,
        ticket_user_id: int,
    ) -> bool:
        return requester_role == UserRole.ADMIN.value or requester_user_id == ticket_user_id

    @staticmethod
    def _row_to_ticket(row: sqlite3.Row) -> SupportTicket:
        return SupportTicket(
            ticket_id=SupportService._row_int(row, "id"),
            user_id=SupportService._row_int(row, "user_id"),
            title=str(row["title"]),
            status=SupportTicketStatus(str(row["status"])),
            created_at_ms=SupportService._row_int(row, "created_at_ms"),
            updated_at_ms=SupportService._row_int(row, "updated_at_ms"),
            last_message_at_ms=SupportService._row_int(row, "last_message_at_ms"),
        )

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> SupportMessage:
        return SupportMessage(
            message_id=SupportService._row_int(row, "id"),
            ticket_id=SupportService._row_int(row, "ticket_id"),
            author_user_id=SupportService._row_int(row, "author_user_id"),
            body_text=str(row["body_text"]),
            created_at_ms=SupportService._row_int(row, "created_at_ms"),
        )

    @staticmethod
    def _row_int(row: sqlite3.Row, key: str) -> int:
        value = row[key]
        if value is None:
            raise SupportError("invalid_data", f"{key} is missing", 500)
        return int(value)

    @staticmethod
    def _lastrowid(cursor: sqlite3.Cursor) -> int:
        value = cursor.lastrowid
        if value is None:
            raise SupportError("invalid_data", "lastrowid is missing", 500)
        return int(value)
