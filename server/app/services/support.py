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
    SupportTicketKind,
    SupportTicketStatus,
    UserRole,
    UserStatus,
)
from app.services.media import MAX_ATTACHMENTS_PER_MESSAGE, MediaService


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
    def __init__(self, db_path: str | Path, storage_root: str | Path | None = None) -> None:
        self._db_path = Path(db_path)
        self._storage_root = Path(storage_root) if storage_root is not None else self._db_path.parent.parent

    def create_ticket(self, *, requester_user_id: int, draft: SupportTicketDraft) -> SupportTicket:
        with self._connect() as connection:
            requester = self._require_support_user(connection, requester_user_id)

            kind = draft.kind if isinstance(draft.kind, SupportTicketKind) else SupportTicketKind(str(draft.kind))
            target_user_id = draft.target_user_id
            if kind == SupportTicketKind.REPORT:
                if not target_user_id:
                    raise SupportError("target_required", "Report requires target_user_id", 422)
                if int(target_user_id) == requester_user_id:
                    raise SupportError("invalid_target", "Cannot report yourself", 422)
                target = connection.execute(
                    "SELECT id FROM users WHERE id = ?",
                    (int(target_user_id),),
                ).fetchone()
                if target is None:
                    raise SupportError("target_not_found", "Reported user was not found", 404)
                target_user_id = int(target_user_id)
            else:
                target_user_id = None

            now_ms = _now_ms()
            ticket_cursor = connection.execute(
                """
                INSERT INTO support_tickets(
                    user_id,
                    title,
                    status,
                    created_at_ms,
                    updated_at_ms,
                    last_message_at_ms,
                    kind,
                    target_user_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    requester_user_id,
                    draft.title.strip(),
                    SupportTicketStatus.OPEN.value,
                    now_ms,
                    now_ms,
                    now_ms,
                    kind.value,
                    target_user_id,
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
            message_row = connection.execute(
                "SELECT id FROM support_messages WHERE ticket_id = ? ORDER BY id DESC LIMIT 1",
                (ticket_id,),
            ).fetchone()
            if message_row is not None:
                self._attach_media_to_message(
                    connection,
                    message_id=int(message_row["id"]),
                    attachment_ids=self._normalize_attachment_ids(draft.attachment_ids),
                    actor_user_id=requester_user_id,
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
            messages = [self._row_to_message(row) for row in rows]
            attachments_by_id = MediaService(self._db_path, self._storage_root).list_for_support_messages(
                connection,
                [message.message_id for message in messages],
            )
            return [
                self._with_message_attachments(message, attachments_by_id=attachments_by_id)
                for message in messages
            ]

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
            self._attach_media_to_message(
                connection,
                message_id=message_id,
                attachment_ids=self._normalize_attachment_ids(draft.attachment_ids),
                actor_user_id=author_user_id,
            )

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
            message = self._row_to_message(row)
            attachments_by_id = MediaService(self._db_path, self._storage_root).list_for_support_messages(
                connection,
                [message.message_id],
            )
            return self._with_message_attachments(message, attachments_by_id=attachments_by_id)

    def set_ticket_status(
        self,
        *,
        ticket_id: int,
        actor_user_id: int,
        status: SupportTicketStatus,
    ) -> SupportTicket:
        with self._connect() as connection:
            actor = self._require_support_user(connection, actor_user_id)
            ticket = self._require_ticket(connection, ticket_id)
            is_admin = str(actor["role"]) == UserRole.ADMIN.value
            is_owner = int(actor["id"]) == int(ticket["user_id"])
            if not is_admin and not is_owner:
                raise SupportError("admin_only", "Only admin or ticket owner can change status", 403)
            if is_owner and not is_admin and status not in {SupportTicketStatus.CLOSED}:
                raise SupportError("owner_close_only", "Ticket owner can only close the ticket", 403)

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
        kind = SupportTicketKind.SUPPORT
        target_user_id: int | None = None
        try:
            raw_kind = row["kind"]
            if raw_kind:
                kind = SupportTicketKind(str(raw_kind))
        except Exception:
            pass
        try:
            raw_target = row["target_user_id"]
            if raw_target is not None:
                target_user_id = int(raw_target)
        except Exception:
            pass
        return SupportTicket(
            ticket_id=SupportService._row_int(row, "id"),
            user_id=SupportService._row_int(row, "user_id"),
            title=str(row["title"]),
            status=SupportTicketStatus(str(row["status"])),
            created_at_ms=SupportService._row_int(row, "created_at_ms"),
            updated_at_ms=SupportService._row_int(row, "updated_at_ms"),
            last_message_at_ms=SupportService._row_int(row, "last_message_at_ms"),
            kind=kind,
            target_user_id=target_user_id,
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
    def _with_message_attachments(
        message: SupportMessage,
        *,
        attachments_by_id: dict[int, tuple[object, ...]],
    ) -> SupportMessage:
        return SupportMessage(
            message_id=message.message_id,
            ticket_id=message.ticket_id,
            author_user_id=message.author_user_id,
            body_text=message.body_text,
            created_at_ms=message.created_at_ms,
            attachments=attachments_by_id.get(message.message_id, ()),
        )

    @staticmethod
    def _normalize_attachment_ids(attachment_ids: tuple[int, ...]) -> tuple[int, ...]:
        ids = tuple(dict.fromkeys(int(value) for value in attachment_ids if int(value) > 0))
        if len(ids) > MAX_ATTACHMENTS_PER_MESSAGE:
            raise SupportError("too_many_attachments", "Too many attachments for one message", 422)
        return ids

    @staticmethod
    def _attach_media_to_message(
        connection: sqlite3.Connection,
        *,
        message_id: int,
        attachment_ids: tuple[int, ...],
        actor_user_id: int,
    ) -> None:
        for position, attachment_id in enumerate(attachment_ids):
            row = connection.execute(
                "SELECT owner_user_id FROM media_attachments WHERE id = ?",
                (attachment_id,),
            ).fetchone()
            if row is None:
                raise SupportError("attachment_not_found", "Attachment not found", 404)
            if int(row["owner_user_id"]) != actor_user_id:
                raise SupportError("forbidden_attachment", "Cannot attach a file owned by another user", 403)
            connection.execute(
                """
                INSERT OR IGNORE INTO support_message_attachments(message_id, attachment_id, position)
                VALUES (?, ?, ?)
                """,
                (message_id, attachment_id, position),
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
