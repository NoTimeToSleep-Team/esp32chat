from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from time import time

from app.models import (
    ChatDraft,
    ChatKind,
    ChatMember,
    ChatMemberRole,
    ChatMessage,
    ChatRoom,
    MessageDraft,
    UserRole,
    UserStatus,
)
from app.services.chat_limits import ChatLimitsService
from app.services.media import MAX_ATTACHMENTS_PER_MESSAGE, MediaError, MediaService


def _now_ms() -> int:
    return int(time() * 1000)


@dataclass(frozen=True)
class ChatError(RuntimeError):
    code: str
    message: str
    status_code: int

    def __str__(self) -> str:
        return self.message


class ChatService:
    def __init__(self, db_path: str | Path, storage_root: str | Path | None = None) -> None:
        self._db_path = Path(db_path)
        self._storage_root = Path(storage_root) if storage_root is not None else self._db_path.parent.parent
        self._limits = ChatLimitsService()

    def ensure_default_common_chat(self, *, title: str = "General") -> ChatRoom:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM chats WHERE kind = ? AND title = ? ORDER BY id LIMIT 1",
                (ChatKind.COMMON.value, title.strip()),
            ).fetchone()
            if row is not None:
                return self._row_to_chat(row)

            now_ms = _now_ms()
            cursor = connection.execute(
                """
                INSERT INTO chats(
                    kind,
                    title,
                    description,
                    owner_user_id,
                    is_private,
                    room_code_hash,
                    avatar_url,
                    created_at_ms,
                    updated_at_ms
                )
                VALUES (?, ?, NULL, NULL, 0, NULL, NULL, ?, ?)
                """,
                (ChatKind.COMMON.value, title.strip(), now_ms, now_ms),
            )
            chat_id = self._lastrowid(cursor)

            created = connection.execute(
                "SELECT * FROM chats WHERE id = ?",
                (chat_id,),
            ).fetchone()
            if created is None:
                raise ChatError("chat_create_failed", "Failed to create default common chat", 500)
            return self._row_to_chat(created)

    def create_common_chat(self, *, actor_user_id: int, draft: ChatDraft) -> ChatRoom:
        with self._connect() as connection:
            actor = self._require_active_user(connection, actor_user_id)
            if actor["role"] != UserRole.ADMIN.value:
                raise ChatError("admin_only", "Only admin can create common chat", 403)

            now_ms = _now_ms()
            cursor = connection.execute(
                """
                INSERT INTO chats(
                    kind,
                    title,
                    description,
                    owner_user_id,
                    is_private,
                    room_code_hash,
                    avatar_url,
                    created_at_ms,
                    updated_at_ms
                )
                VALUES (?, ?, ?, ?, 0, NULL, NULL, ?, ?)
                """,
                (
                    ChatKind.COMMON.value,
                    draft.title.strip(),
                    (draft.description or "").strip() or None,
                    self._row_int(actor, "id"),
                    now_ms,
                    now_ms,
                ),
            )
            chat_id = self._lastrowid(cursor)
            row = connection.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
            if row is None:
                raise ChatError("chat_create_failed", "Failed to create common chat", 500)
            return self._row_to_chat(row)

    def create_custom_chat(
        self,
        *,
        creator_user_id: int,
        draft: ChatDraft,
        is_private: bool = False,
        room_code: str | None = None,
        avatar_url: str | None = None,
    ) -> ChatRoom:
        with self._connect() as connection:
            decision = self._limits.evaluate_custom_chat_creation(
                connection,
                user_id=creator_user_id,
            )
            if not decision.allowed:
                raise ChatError(
                    decision.reason_code or "custom_chat_forbidden",
                    decision.reason_message or "Cannot create custom chat",
                    decision.status_code,
                )

            creator = self._require_active_user(connection, creator_user_id)

            normalized_code = self._normalize_room_code(room_code)
            normalized_avatar = (avatar_url or "").strip() or None

            private_flag = is_private or (normalized_code is not None)
            room_code_hash = (
                self._hash_room_code(normalized_code)
                if normalized_code is not None
                else None
            )

            now_ms = _now_ms()
            cursor = connection.execute(
                """
                INSERT INTO chats(
                    kind,
                    title,
                    description,
                    owner_user_id,
                    is_private,
                    room_code_hash,
                    avatar_url,
                    created_at_ms,
                    updated_at_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ChatKind.CUSTOM.value,
                    draft.title.strip(),
                    (draft.description or "").strip() or None,
                    self._row_int(creator, "id"),
                    1 if private_flag else 0,
                    room_code_hash,
                    normalized_avatar,
                    now_ms,
                    now_ms,
                ),
            )
            chat_id = self._lastrowid(cursor)

            connection.execute(
                """
                INSERT OR IGNORE INTO chat_members(chat_id, user_id, role, joined_at_ms)
                VALUES (?, ?, ?, ?)
                """,
                (
                    chat_id,
                    self._row_int(creator, "id"),
                    ChatMemberRole.OWNER.value,
                    now_ms,
                ),
            )

            row = connection.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
            if row is None:
                raise ChatError("chat_create_failed", "Failed to create custom chat", 500)
            return self._row_to_chat(row)

    def list_user_chats(self, *, user_id: int) -> list[ChatRoom]:
        with self._connect() as connection:
            user = self._require_active_user(connection, user_id)

            rows = connection.execute(
                    """
                    SELECT c.*
                    FROM chats c
                    WHERE c.kind = ?
                       OR EXISTS(
                            SELECT 1
                            FROM chat_members m
                            WHERE m.chat_id = c.id
                              AND m.user_id = ?
                       )
                    ORDER BY c.updated_at_ms DESC, c.id DESC
                    """,
                    (ChatKind.COMMON.value, user_id),
                ).fetchall()

            return [self._row_to_chat(row) for row in rows]

    def list_updates(
        self,
        *,
        user_id: int,
        since_ms: int,
        limit: int = 50,
    ) -> list[dict[str, object]]:
        """New messages in all chats available to the user (excluding own)."""
        safe_limit = min(max(int(limit), 1), 200)
        safe_since = max(int(since_ms), 0)
        with self._connect() as connection:
            self._require_active_user(connection, user_id)
            rows = connection.execute(
                """
                SELECT
                    m.id AS message_id,
                    m.chat_id AS chat_id,
                    c.title AS chat_title,
                    m.author_user_id AS author_user_id,
                    u.login AS author_login,
                    m.body_text AS body_text,
                    m.created_at_ms AS created_at_ms
                FROM chat_messages m
                JOIN chats c ON c.id = m.chat_id
                LEFT JOIN users u ON u.id = m.author_user_id
                WHERE m.created_at_ms > ?
                  AND m.author_user_id != ?
                  AND (
                        c.kind = ?
                     OR EXISTS(
                            SELECT 1
                            FROM chat_members cm
                            WHERE cm.chat_id = c.id
                              AND cm.user_id = ?
                        )
                  )
                ORDER BY m.created_at_ms DESC
                LIMIT ?
                """,
                (safe_since, user_id, ChatKind.COMMON.value, user_id, safe_limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def add_member(
        self,
        *,
        chat_id: int,
        target_user_id: int,
        actor_user_id: int,
    ) -> ChatMember:
        with self._connect() as connection:
            actor = self._require_active_user(connection, actor_user_id)
            self._require_active_user(connection, target_user_id)
            chat = self._require_chat(connection, chat_id)

            if chat["kind"] != ChatKind.CUSTOM.value:
                raise ChatError(
                    "invalid_chat_kind",
                    "Members are managed only for custom chats",
                    409,
                )

            if actor["role"] != UserRole.ADMIN.value and not self._is_owner(
                connection,
                chat_id=chat_id,
                user_id=actor_user_id,
            ):
                raise ChatError("forbidden", "Only owner or admin can add members", 403)

            now_ms = _now_ms()
            connection.execute(
                """
                INSERT OR IGNORE INTO chat_members(chat_id, user_id, role, joined_at_ms)
                VALUES (?, ?, ?, ?)
                """,
                (chat_id, target_user_id, ChatMemberRole.MEMBER.value, now_ms),
            )

            row = connection.execute(
                "SELECT * FROM chat_members WHERE chat_id = ? AND user_id = ?",
                (chat_id, target_user_id),
            ).fetchone()
            if row is None:
                raise ChatError("member_add_failed", "Failed to add member", 500)
            return self._row_to_member(row)

    def join_private_chat(
        self,
        *,
        chat_id: int,
        user_id: int,
        room_code: str | None = None,
    ) -> ChatMember:
        with self._connect() as connection:
            user = self._require_active_user(connection, user_id)
            chat = self._require_chat(connection, chat_id)

            if str(chat["kind"]) != ChatKind.CUSTOM.value:
                raise ChatError(
                    "invalid_chat_kind",
                    "Private join is available only for custom chats",
                    409,
                )

            existing = connection.execute(
                "SELECT * FROM chat_members WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id),
            ).fetchone()
            if existing is not None:
                return self._row_to_member(existing)

            if str(user["role"]) != UserRole.ADMIN.value:
                if self._row_bool(chat, "is_private"):
                    code_hash = self._row_optional_str(chat, "room_code_hash")
                    if code_hash:
                        normalized_code = self._normalize_room_code(room_code)
                        if normalized_code is None or not self._verify_room_code(
                            normalized_code,
                            code_hash,
                        ):
                            raise ChatError("invalid_room_code", "Invalid room code", 403)

            now_ms = _now_ms()
            connection.execute(
                """
                INSERT OR IGNORE INTO chat_members(chat_id, user_id, role, joined_at_ms)
                VALUES (?, ?, ?, ?)
                """,
                (chat_id, user_id, ChatMemberRole.MEMBER.value, now_ms),
            )

            row = connection.execute(
                "SELECT * FROM chat_members WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id),
            ).fetchone()
            if row is None:
                raise ChatError("member_add_failed", "Failed to join private chat", 500)
            return self._row_to_member(row)

    def list_members(self, *, chat_id: int, requester_user_id: int) -> list[ChatMember]:
        with self._connect() as connection:
            self._require_active_user(connection, requester_user_id)
            chat = self._require_chat(connection, chat_id)

            if not self._can_access_chat(connection, chat_row=chat, user_id=requester_user_id):
                raise ChatError("forbidden", "User has no access to this chat", 403)

            rows = connection.execute(
                """
                SELECT *
                FROM chat_members
                WHERE chat_id = ?
                ORDER BY joined_at_ms ASC, user_id ASC
                """,
                (chat_id,),
            ).fetchall()
            return [self._row_to_member(row) for row in rows]

    def configure_private_room(
        self,
        *,
        chat_id: int,
        actor_user_id: int,
        title: str | None = None,
        description: str | None = None,
        avatar_url: str | None = None,
        room_code: str | None = None,
        is_private: bool | None = None,
    ) -> ChatRoom:
        with self._connect() as connection:
            actor = self._require_active_user(connection, actor_user_id)
            chat = self._require_chat(connection, chat_id)

            if str(chat["kind"]) != ChatKind.CUSTOM.value:
                raise ChatError(
                    "invalid_chat_kind",
                    "Private room configuration is available only for custom chats",
                    409,
                )

            is_admin = str(actor["role"]) == UserRole.ADMIN.value
            is_owner = self._is_owner(connection, chat_id=chat_id, user_id=actor_user_id)
            if not is_admin and not is_owner:
                raise ChatError(
                    "forbidden",
                    "Only owner or admin can update private room config",
                    403,
                )

            next_title = title.strip() if title is not None else str(chat["title"])
            next_description = (
                (description or "").strip() or None
                if description is not None
                else self._row_optional_str(chat, "description")
            )
            next_avatar = (
                (avatar_url or "").strip() or None
                if avatar_url is not None
                else self._row_optional_str(chat, "avatar_url")
            )

            code_hash = self._row_optional_str(chat, "room_code_hash")
            if room_code is not None:
                if room_code == "":
                    code_hash = None
                else:
                    normalized_code = self._normalize_room_code(room_code)
                    if normalized_code is None:
                        raise ChatError(
                            "invalid_room_code",
                            "Room code must contain exactly 4 digits",
                            422,
                        )
                    code_hash = self._hash_room_code(normalized_code)

            if is_private is None:
                private_flag = self._row_bool(chat, "is_private") or bool(code_hash)
            else:
                private_flag = bool(is_private)
                if not private_flag:
                    code_hash = None

            now_ms = _now_ms()
            connection.execute(
                """
                UPDATE chats
                SET title = ?,
                    description = ?,
                    is_private = ?,
                    room_code_hash = ?,
                    avatar_url = ?,
                    updated_at_ms = ?
                WHERE id = ?
                """,
                (
                    next_title,
                    next_description,
                    1 if private_flag else 0,
                    code_hash,
                    next_avatar,
                    now_ms,
                    chat_id,
                ),
            )

            updated = connection.execute(
                "SELECT * FROM chats WHERE id = ?",
                (chat_id,),
            ).fetchone()
            if updated is None:
                raise ChatError("chat_not_found", "Chat not found", 404)
            return self._row_to_chat(updated)

    def send_message(
        self,
        *,
        chat_id: int,
        author_user_id: int,
        draft: MessageDraft,
    ) -> ChatMessage:
        with self._connect() as connection:
            self._require_active_user(connection, author_user_id)
            chat = self._require_chat(connection, chat_id)

            if not self._can_access_chat(connection, chat_row=chat, user_id=author_user_id):
                raise ChatError("forbidden", "User has no access to this chat", 403)

            now_ms = _now_ms()
            text = draft.body_text.strip()
            client_message_id = (draft.client_message_id or "").strip() or None
            attachment_ids = self._normalize_attachment_ids(draft.attachment_ids)

            try:
                cursor = connection.execute(
                    """
                    INSERT INTO chat_messages(
                        chat_id,
                        author_user_id,
                        body_text,
                        client_message_id,
                        created_at_ms,
                        edited_at_ms
                    )
                    VALUES (?, ?, ?, ?, ?, NULL)
                    """,
                    (chat_id, author_user_id, text, client_message_id, now_ms),
                )
                message_id = self._lastrowid(cursor)
                self._attach_media_to_message(
                    connection,
                    message_id=message_id,
                    attachment_ids=attachment_ids,
                    actor_user_id=author_user_id,
                )
            except sqlite3.IntegrityError as exc:
                if client_message_id:
                    row = connection.execute(
                        """
                        SELECT * FROM chat_messages
                        WHERE chat_id = ? AND client_message_id = ?
                        """,
                        (chat_id, client_message_id),
                    ).fetchone()
                    if row is not None:
                        message = self._row_to_message(row)
                        return self._with_message_attachments(connection, message)
                raise ChatError("message_create_failed", "Failed to save chat message", 409) from exc
            except MediaError as exc:
                raise ChatError(exc.code, exc.message, exc.status_code) from exc

            connection.execute(
                "UPDATE chats SET updated_at_ms = ? WHERE id = ?",
                (now_ms, chat_id),
            )

            row = self._select_message_row(connection, message_id)
            if row is None:
                raise ChatError("message_create_failed", "Failed to save chat message", 500)
            return self._with_message_attachments(connection, self._row_to_message(row))

    def list_messages(
        self,
        *,
        chat_id: int,
        requester_user_id: int,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ChatMessage]:
        safe_limit = min(max(limit, 1), 500)
        safe_offset = max(offset, 0)

        with self._connect() as connection:
            self._require_active_user(connection, requester_user_id)
            chat = self._require_chat(connection, chat_id)

            if not self._can_access_chat(connection, chat_row=chat, user_id=requester_user_id):
                raise ChatError("forbidden", "User has no access to this chat", 403)

            rows = connection.execute(
                """
                SELECT m.*, u.login AS author_login, u.avatar_emoji AS author_avatar_emoji
                FROM chat_messages m
                LEFT JOIN users u ON u.id = m.author_user_id
                WHERE m.chat_id = ?
                ORDER BY m.created_at_ms DESC, m.id DESC
                LIMIT ? OFFSET ?
                """,
                (chat_id, safe_limit, safe_offset),
            ).fetchall()
            # Offset counts from the newest message; return oldest-first for rendering.
            rows = list(reversed(rows))
            messages = [self._row_to_message(row) for row in rows]
            attachments_by_id = MediaService(self._db_path, self._storage_root).list_for_chat_messages(
                connection,
                [message.message_id for message in messages],
            )
            return [
                self._with_message_attachments(
                    connection,
                    message,
                    attachments_by_id=attachments_by_id,
                )
                for message in messages
            ]

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _require_active_user(connection: sqlite3.Connection, user_id: int) -> sqlite3.Row:
        row = connection.execute(
            "SELECT id, role, status FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            raise ChatError("user_not_found", "User not found", 404)
        if str(row["status"]) != UserStatus.ACTIVE.value:
            raise ChatError("user_inactive", "User is blocked or banned", 403)
        return row

    @staticmethod
    def _require_chat(connection: sqlite3.Connection, chat_id: int) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM chats WHERE id = ?",
            (chat_id,),
        ).fetchone()
        if row is None:
            raise ChatError("chat_not_found", "Chat not found", 404)
        return row

    def _can_access_chat(
        self,
        connection: sqlite3.Connection,
        *,
        chat_row: sqlite3.Row,
        user_id: int,
    ) -> bool:
        if self._is_admin(connection, user_id=user_id):
            return True

        kind = str(chat_row["kind"])
        if kind == ChatKind.COMMON.value:
            return True

        owner_user_id = self._row_optional_int(chat_row, "owner_user_id")
        if owner_user_id == user_id:
            return True

        member = connection.execute(
            "SELECT 1 FROM chat_members WHERE chat_id = ? AND user_id = ?",
            (self._row_int(chat_row, "id"), user_id),
        ).fetchone()
        return member is not None

    @staticmethod
    def _is_admin(connection: sqlite3.Connection, *, user_id: int) -> bool:
        row = connection.execute(
            "SELECT role FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            return False
        return str(row["role"]) == UserRole.ADMIN.value

    @staticmethod
    def _is_owner(connection: sqlite3.Connection, *, chat_id: int, user_id: int) -> bool:
        row = connection.execute(
            """
            SELECT 1
            FROM chat_members
            WHERE chat_id = ?
              AND user_id = ?
              AND role = ?
            """,
            (chat_id, user_id, ChatMemberRole.OWNER.value),
        ).fetchone()
        return row is not None

    @staticmethod
    def _row_to_chat(row: sqlite3.Row) -> ChatRoom:
        return ChatRoom(
            chat_id=ChatService._row_int(row, "id"),
            kind=ChatKind(str(row["kind"])),
            title=str(row["title"]),
            description=ChatService._row_optional_str(row, "description"),
            owner_user_id=ChatService._row_optional_int(row, "owner_user_id"),
            is_private=ChatService._row_bool(row, "is_private"),
            avatar_url=ChatService._row_optional_str(row, "avatar_url"),
            has_room_code=bool(ChatService._row_optional_str(row, "room_code_hash")),
            created_at_ms=ChatService._row_int(row, "created_at_ms"),
            updated_at_ms=ChatService._row_int(row, "updated_at_ms"),
        )

    @staticmethod
    def _row_to_member(row: sqlite3.Row) -> ChatMember:
        return ChatMember(
            chat_id=ChatService._row_int(row, "chat_id"),
            user_id=ChatService._row_int(row, "user_id"),
            role=ChatMemberRole(str(row["role"])),
            joined_at_ms=ChatService._row_int(row, "joined_at_ms"),
        )

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> ChatMessage:
        return ChatMessage(
            message_id=ChatService._row_int(row, "id"),
            chat_id=ChatService._row_int(row, "chat_id"),
            author_user_id=ChatService._row_int(row, "author_user_id"),
            body_text=str(row["body_text"]),
            client_message_id=ChatService._row_optional_str(row, "client_message_id"),
            created_at_ms=ChatService._row_int(row, "created_at_ms"),
            edited_at_ms=ChatService._row_optional_int(row, "edited_at_ms"),
            author_login=ChatService._row_optional_str_lenient(row, "author_login"),
            author_avatar_emoji=ChatService._row_optional_str_lenient(row, "author_avatar_emoji"),
        )

    def _with_message_attachments(
        self,
        connection: sqlite3.Connection,
        message: ChatMessage,
        *,
        attachments_by_id: dict[int, tuple[object, ...]] | None = None,
    ) -> ChatMessage:
        if attachments_by_id is None:
            attachments_by_id = MediaService(self._db_path, self._storage_root).list_for_chat_messages(
                connection,
                [message.message_id],
            )
        return ChatMessage(
            message_id=message.message_id,
            chat_id=message.chat_id,
            author_user_id=message.author_user_id,
            body_text=message.body_text,
            client_message_id=message.client_message_id,
            created_at_ms=message.created_at_ms,
            edited_at_ms=message.edited_at_ms,
            attachments=attachments_by_id.get(message.message_id, ()),
            author_login=message.author_login,
            author_avatar_emoji=message.author_avatar_emoji,
        )

    @staticmethod
    def _normalize_attachment_ids(attachment_ids: tuple[int, ...]) -> tuple[int, ...]:
        ids = tuple(dict.fromkeys(int(value) for value in attachment_ids if int(value) > 0))
        if len(ids) > MAX_ATTACHMENTS_PER_MESSAGE:
            raise ChatError("too_many_attachments", "Too many attachments for one message", 422)
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
                raise ChatError("attachment_not_found", "Attachment not found", 404)
            if int(row["owner_user_id"]) != actor_user_id:
                raise ChatError("forbidden_attachment", "Cannot attach a file owned by another user", 403)
            connection.execute(
                """
                INSERT OR IGNORE INTO chat_message_attachments(message_id, attachment_id, position)
                VALUES (?, ?, ?)
                """,
                (message_id, attachment_id, position),
            )

    @staticmethod
    def _normalize_room_code(room_code: str | None) -> str | None:
        if room_code is None:
            return None
        normalized = room_code.strip()
        if normalized == "":
            return None
        if len(normalized) != 4 or not normalized.isdigit():
            raise ChatError(
                "invalid_room_code",
                "Room code must contain exactly 4 digits",
                422,
            )
        return normalized

    @staticmethod
    def _hash_room_code(room_code: str) -> str:
        salt = secrets.token_hex(8)
        iterations = 120_000
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            room_code.encode("utf-8"),
            salt.encode("utf-8"),
            iterations,
        ).hex()
        return f"pbkdf2_sha256${iterations}${salt}${digest}"

    @staticmethod
    def _verify_room_code(room_code: str, code_hash: str) -> bool:
        parts = code_hash.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        try:
            iterations = int(parts[1])
        except ValueError:
            return False

        salt = parts[2]
        expected = parts[3]
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            room_code.encode("utf-8"),
            salt.encode("utf-8"),
            iterations,
        ).hex()
        return hmac.compare_digest(actual, expected)

    @staticmethod
    def _row_int(row: sqlite3.Row, key: str) -> int:
        value = row[key]
        if value is None:
            raise ChatError("invalid_data", f"{key} is missing", 500)
        return int(value)

    @staticmethod
    def _row_optional_int(row: sqlite3.Row, key: str) -> int | None:
        value = row[key]
        return int(value) if value is not None else None

    @staticmethod
    def _row_optional_str(row: sqlite3.Row, key: str) -> str | None:
        value = row[key]
        return str(value) if value is not None else None

    @staticmethod
    def _row_optional_str_lenient(row: sqlite3.Row, key: str) -> str | None:
        try:
            value = row[key]
        except Exception:
            return None
        return str(value) if value is not None else None

    @staticmethod
    def _select_message_row(connection: sqlite3.Connection, message_id: int) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT m.*, u.login AS author_login, u.avatar_emoji AS author_avatar_emoji
            FROM chat_messages m
            LEFT JOIN users u ON u.id = m.author_user_id
            WHERE m.id = ?
            """,
            (message_id,),
        ).fetchone()

    @staticmethod
    def _row_bool(row: sqlite3.Row, key: str) -> bool:
        try:
            value = row[key]
        except Exception:
            return False
        if value is None:
            return False
        return bool(int(value))

    @staticmethod
    def _lastrowid(cursor: sqlite3.Cursor) -> int:
        value = cursor.lastrowid
        if value is None:
            raise ChatError("invalid_data", "lastrowid is missing", 500)
        return int(value)

    def get_or_create_dm(self, user_id: int, target_user_id: int) -> ChatRoom:
        import time
        if user_id == target_user_id:
            raise ChatError("invalid_target", "Cannot DM yourself", 400)
        with self._connect() as connection:
            self._require_active_user(connection, user_id)
            self._require_active_user(connection, target_user_id)
            # Check for existing 1-on-1 chat
            rows = connection.execute("""
                SELECT DISTINCT c.id FROM chats c
                JOIN chat_members m1 ON c.id = m1.chat_id AND m1.user_id = ?
                JOIN chat_members m2 ON c.id = m2.chat_id AND m2.user_id = ?
                WHERE c.is_private = 1 AND c.kind = 'custom'
            """, (user_id, target_user_id)).fetchall()
            if rows:
                row = connection.execute("SELECT * FROM chats WHERE id=?", (rows[0][0],)).fetchone()
                if row:
                    return self._row_to_chat(row)
            # Create new DM
            now_ms = int(time.time() * 1000)
            u1 = connection.execute("SELECT login FROM users WHERE id=?", (user_id,)).fetchone()
            u2 = connection.execute("SELECT login FROM users WHERE id=?", (target_user_id,)).fetchone()
            login1 = u1["login"] if u1 else str(user_id)
            login2 = u2["login"] if u2 else str(target_user_id)
            draft_title = f"{login1} & {login2}"
            cursor = connection.execute(
                "INSERT INTO chats (kind, title, description, owner_user_id, is_private, created_at_ms, updated_at_ms) VALUES (?, ?, ?, ?, 1, ?, ?)",
                (ChatKind.CUSTOM.value, draft_title, "", user_id, now_ms, now_ms),
            )
            chat_id = cursor.lastrowid
            connection.execute("INSERT INTO chat_members (chat_id, user_id, role, joined_at_ms) VALUES (?, ?, 'member', ?)", (chat_id, user_id, now_ms))
            connection.execute("INSERT INTO chat_members (chat_id, user_id, role, joined_at_ms) VALUES (?, ?, 'member', ?)", (chat_id, target_user_id, now_ms))
            connection.commit()
            row = connection.execute("SELECT * FROM chats WHERE id=?", (chat_id,)).fetchone()
            if row is None:
                raise ChatError("create_failed", "DM chat create failed", 500)
            return self._row_to_chat(row)

    def search_users(self, query: str, limit: int = 20) -> list[dict]:
        safe_limit = min(max(limit, 1), 50)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, login FROM users WHERE status='active' AND login LIKE ? ORDER BY login LIMIT ?",
                (f"%{query}%", safe_limit),
            ).fetchall()
            return [{"user_id": int(r["id"]), "login": str(r["login"])} for r in rows]

    def delete_message(self, chat_id: int, message_id: int, actor_user_id: int | None = None) -> None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM chat_messages WHERE id=? AND chat_id=?", (message_id, chat_id)).fetchone()
            if row is None:
                raise ChatError("not_found", "Message not found", 404)
            if actor_user_id is not None:
                is_owner = int(row["author_user_id"]) == actor_user_id
                is_admin = connection.execute("SELECT 1 FROM users WHERE id=? AND role IN ('admin','moderator')", (actor_user_id,)).fetchone() is not None
                if not is_owner and not is_admin:
                    raise ChatError("forbidden", "Not authorized to delete this message", 403)
            connection.execute("DELETE FROM chat_messages WHERE id=?", (message_id,))
            connection.execute("DELETE FROM chat_message_attachments WHERE message_id=?", (message_id,))

    def delete_chat(self, chat_id: int) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM chat_message_attachments WHERE message_id IN (SELECT id FROM chat_messages WHERE chat_id=?)", (chat_id,))
            connection.execute("DELETE FROM chat_messages WHERE chat_id=?", (chat_id,))
            connection.execute("DELETE FROM chat_members WHERE chat_id=?", (chat_id,))
            connection.execute("DELETE FROM chats WHERE id=?", (chat_id,))

    def clear_chat_messages(self, chat_id: int) -> int:
        with self._connect() as connection:
            connection.execute("DELETE FROM chat_message_attachments WHERE message_id IN (SELECT id FROM chat_messages WHERE chat_id=?)", (chat_id,))
            cur = connection.execute("DELETE FROM chat_messages WHERE chat_id=?", (chat_id,))
            return cur.rowcount

    def clear_chat_messages_range(self, chat_id: int, from_ms: int, to_ms: int) -> int:
        with self._connect() as connection:
            connection.execute("DELETE FROM chat_message_attachments WHERE message_id IN (SELECT id FROM chat_messages WHERE chat_id=? AND created_at_ms >= ? AND created_at_ms <= ?)", (chat_id, from_ms, to_ms))
            cur = connection.execute("DELETE FROM chat_messages WHERE chat_id=? AND created_at_ms >= ? AND created_at_ms <= ?", (chat_id, from_ms, to_ms))
            return cur.rowcount

    def full_reset(self, admin_user_id: int) -> dict:
        with self._connect() as connection:
            connection.execute("DELETE FROM chat_message_attachments")
            connection.execute("DELETE FROM chat_messages")
            connection.execute("DELETE FROM chat_members")
            connection.execute("DELETE FROM chats WHERE is_private = 0 OR kind = 'custom'")
            deleted_users = connection.execute("DELETE FROM users WHERE role != 'admin'").rowcount
            connection.execute("DELETE FROM sessions")
            connection.execute("DELETE FROM device_pairings")
            connection.execute("DELETE FROM applications")
            return {"users_deleted": deleted_users, "chats_cleared": True}

    def clear_global_chat(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT id FROM chats WHERE kind = 'common' LIMIT 1").fetchone()
            if not row:
                return 0
            chat_id = int(row[0])
            connection.execute("DELETE FROM chat_message_attachments WHERE message_id IN (SELECT id FROM chat_messages WHERE chat_id=?)", (chat_id,))
            cur = connection.execute("DELETE FROM chat_messages WHERE chat_id=?", (chat_id,))
            return cur.rowcount

    def delete_all_chats(self) -> int:
        with self._connect() as connection:
            connection.execute("DELETE FROM chat_message_attachments")
            connection.execute("DELETE FROM chat_messages")
            connection.execute("DELETE FROM chat_members")
            cur = connection.execute("DELETE FROM chats WHERE kind != 'common'")
            return cur.rowcount

    def delete_all_users(self, admin_user_id: int) -> int:
        with self._connect() as connection:
            count = connection.execute("DELETE FROM users WHERE id != ?", (admin_user_id,)).rowcount
            connection.execute("DELETE FROM sessions WHERE user_id != ?", (admin_user_id,))
            connection.execute("DELETE FROM device_pairings WHERE user_id != ?", (admin_user_id,))
            return count

    def get_message_author(self, message_id: int):
        with self._connect() as connection:
            row = connection.execute("SELECT author_user_id FROM chat_messages WHERE id = ?", (message_id,)).fetchone()
            return row[0] if row else None

    def edit_message(self, chat_id: int, message_id: int, actor_user_id: int, body_text: str):
        with self._connect() as connection:
            msg = connection.execute("SELECT * FROM chat_messages WHERE id = ? AND chat_id = ?", (message_id, chat_id)).fetchone()
            if not msg:
                raise ChatError("message_not_found", "Message not found", 404)
            if int(msg["author_user_id"]) != actor_user_id:
                raise ChatError("forbidden", "Only the author can edit this message", 403)
            now_ms = _now_ms()
            connection.execute("UPDATE chat_messages SET body_text = ?, edited_at_ms = ? WHERE id = ?", (body_text, now_ms, message_id))
            connection.commit()
            updated_row = self._select_message_row(connection, message_id)
            if updated_row is None:
                raise ChatError("message_not_found", "Message not found", 404)
            return self._row_to_message(updated_row)
