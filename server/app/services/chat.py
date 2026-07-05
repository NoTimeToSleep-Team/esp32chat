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
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
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

            if str(user["role"]) == UserRole.ADMIN.value:
                rows = connection.execute(
                    """
                    SELECT c.*
                    FROM chats c
                    ORDER BY c.updated_at_ms DESC, c.id DESC
                    """
                ).fetchall()
            else:
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
                        return self._row_to_message(row)
                raise ChatError("message_create_failed", "Failed to save chat message", 409) from exc

            connection.execute(
                "UPDATE chats SET updated_at_ms = ? WHERE id = ?",
                (now_ms, chat_id),
            )

            row = connection.execute(
                "SELECT * FROM chat_messages WHERE id = ?",
                (message_id,),
            ).fetchone()
            if row is None:
                raise ChatError("message_create_failed", "Failed to save chat message", 500)
            return self._row_to_message(row)

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
                SELECT *
                FROM chat_messages
                WHERE chat_id = ?
                ORDER BY created_at_ms ASC, id ASC
                LIMIT ? OFFSET ?
                """,
                (chat_id, safe_limit, safe_offset),
            ).fetchall()
            return [self._row_to_message(row) for row in rows]

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
