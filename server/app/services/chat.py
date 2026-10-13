from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from time import time

from app.models import (
    CHAT_PERMISSIONS,
    REACTION_EMOJIS,
    AvatarImage,
    ChatDraft,
    ChatInvite,
    ChatJoinRequest,
    ChatKind,
    ChatMember,
    ChatMemberRole,
    ChatMessage,
    ChatPoll,
    ChatPollOption,
    ChatReaction,
    ChatRoom,
    ChatType,
    MessageDraft,
    UserRole,
    UserStatus,
    default_admin_permissions,
)
from app.services.chat_limits import ChatLimitsService
from app.services.media import MAX_ATTACHMENTS_PER_MESSAGE, MediaError, MediaService


def _now_ms() -> int:
    return int(time() * 1000)


_CHAT_AVATAR_EXT_BY_MIME = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}

_CHAT_AVATAR_MIME_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}

MAX_CHAT_AVATAR_BYTES = 2_000_000


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
        member_ids: Sequence[int] | None = None,
        require_members: bool = False,
        chat_type: ChatType | None = None,
        username: str | None = None,
        is_public: bool | None = None,
        history_visible: bool | None = None,
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

            resolved_member_ids = self._resolve_member_ids(
                connection,
                creator_user_id=self._row_int(creator, "id"),
                member_ids=member_ids,
            )
            if require_members and not resolved_member_ids:
                raise ChatError(
                    "members_required",
                    "Add at least one member to create a chat",
                    422,
                )

            normalized_code = self._normalize_room_code(room_code)
            normalized_avatar = (avatar_url or "").strip() or None

            private_flag = is_private or (normalized_code is not None)
            room_code_hash = (
                self._hash_room_code(normalized_code)
                if normalized_code is not None
                else None
            )

            resolved_type = chat_type or draft.chat_type or ChatType.GROUP
            if private_flag and resolved_type == ChatType.GROUP and (normalized_code is not None or is_private):
                # legacy private rooms stay groups
                resolved_type = ChatType.GROUP
            if resolved_type == ChatType.DM:
                raise ChatError("invalid_chat_type", "Direct chats are created separately", 422)

            resolved_username = self._normalize_username(username if username is not None else draft.username)
            if resolved_username:
                self._require_username_free(connection, username=resolved_username)

            resolved_public = bool(is_public if is_public is not None else draft.is_public)
            resolved_history = bool(
                history_visible if history_visible is not None else draft.history_visible
            )
            member_role = (
                ChatMemberRole.SUBSCRIBER.value
                if resolved_type == ChatType.CHANNEL
                else ChatMemberRole.MEMBER.value
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
                    updated_at_ms,
                    chat_type,
                    username,
                    is_public,
                    history_visible
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    resolved_type.value,
                    resolved_username,
                    1 if resolved_public else 0,
                    1 if resolved_history else 0,
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

            for member_user_id in resolved_member_ids:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO chat_members(chat_id, user_id, role, joined_at_ms)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        chat_id,
                        member_user_id,
                        member_role,
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
        role: ChatMemberRole | None = None,
    ) -> ChatMember:
        with self._connect() as connection:
            actor = self._require_active_user(connection, actor_user_id)
            self._require_active_user(connection, target_user_id)
            chat = self._require_chat(connection, chat_id)

            if str(chat["kind"]) != ChatKind.CUSTOM.value:
                raise ChatError(
                    "invalid_chat_kind",
                    "Members are managed only for custom chats",
                    409,
                )

            if target_user_id != actor_user_id and not self._has_permission(
                connection,
                chat_row=chat,
                user_id=actor_user_id,
                permission="invite_users",
            ):
                raise ChatError("forbidden", "Only the owner or an admin can add members", 403)

            chat_type = self._row_optional_str_lenient(chat, "chat_type") or ChatType.GROUP.value
            default_role = (
                ChatMemberRole.SUBSCRIBER.value
                if chat_type == ChatType.CHANNEL.value
                else ChatMemberRole.MEMBER.value
            )
            resolved_role = role.value if role is not None else default_role
            if resolved_role == ChatMemberRole.OWNER.value:
                raise ChatError("invalid_role", "Use ownership transfer to change the owner", 422)

            now_ms = _now_ms()
            connection.execute(
                """
                INSERT OR IGNORE INTO chat_members(chat_id, user_id, role, joined_at_ms)
                VALUES (?, ?, ?, ?)
                """,
                (chat_id, target_user_id, resolved_role, now_ms),
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

    def list_member_profiles(self, *, chat_id: int, requester_user_id: int) -> list[dict[str, object]]:
        """Members with their login/avatar/role for the chat profile screen."""
        with self._connect() as connection:
            self._require_active_user(connection, requester_user_id)
            chat = self._require_chat(connection, chat_id)

            if not self._can_access_chat(connection, chat_row=chat, user_id=requester_user_id):
                raise ChatError("forbidden", "User has no access to this chat", 403)

            rows = connection.execute(
                """
                SELECT m.user_id AS user_id,
                       m.role AS role,
                       m.joined_at_ms AS joined_at_ms,
                       m.permissions AS permissions,
                       m.is_muted AS is_muted,
                       m.is_archived AS is_archived,
                       m.is_pinned AS is_pinned,
                       u.login AS login,
                       u.avatar_emoji AS avatar_emoji,
                       u.avatar_path AS avatar_path,
                       u.avatar_updated_at_ms AS avatar_updated_at_ms,
                       u.status AS status
                FROM chat_members m
                LEFT JOIN users u ON u.id = m.user_id
                WHERE m.chat_id = ?
                ORDER BY CASE m.role WHEN 'owner' THEN 0 WHEN 'admin' THEN 1 ELSE 2 END,
                         m.joined_at_ms ASC,
                         m.user_id ASC
                """,
                (chat_id,),
            ).fetchall()

            chat_type = self._row_optional_str_lenient(chat, "chat_type") or ChatType.GROUP.value
            owner_user_id = self._row_optional_int(chat, "owner_user_id")
            items: list[dict[str, object]] = []
            for row in rows:
                user_id = int(row["user_id"])
                role = str(row["role"])
                permissions: dict[str, bool] | None = None
                raw_permissions = self._row_optional_str_lenient(row, "permissions")
                if raw_permissions:
                    try:
                        parsed = json.loads(raw_permissions)
                        if isinstance(parsed, dict):
                            permissions = {name: bool(parsed.get(name, True)) for name in CHAT_PERMISSIONS}
                    except (TypeError, ValueError):
                        permissions = None
                if chat_type == ChatType.CHANNEL.value:
                    can_post = role in {ChatMemberRole.OWNER.value, ChatMemberRole.ADMIN.value}
                else:
                    can_post = role != ChatMemberRole.SUBSCRIBER.value
                items.append(
                    {
                        "user_id": user_id,
                        "login": self._row_optional_str_lenient(row, "login") or f"user#{user_id}",
                        "role": role,
                        "joined_at_ms": int(row["joined_at_ms"]),
                        "avatar_emoji": self._row_optional_str_lenient(row, "avatar_emoji"),
                        "avatar_updated_at_ms": self._row_optional_int_lenient(row, "avatar_updated_at_ms"),
                        "has_avatar": bool(self._row_optional_str_lenient(row, "avatar_path")),
                        "is_owner": owner_user_id == user_id or role == ChatMemberRole.OWNER.value,
                        "is_me": user_id == requester_user_id,
                        "status": self._row_optional_str_lenient(row, "status"),
                        "permissions": permissions,
                        "can_post": can_post,
                        "is_muted": self._row_bool(row, "is_muted"),
                        "is_archived": self._row_bool(row, "is_archived"),
                        "is_pinned": self._row_bool(row, "is_pinned"),
                    }
                )
            return items

    def get_chat(self, *, chat_id: int, requester_user_id: int) -> ChatRoom:
        with self._connect() as connection:
            self._require_active_user(connection, requester_user_id)
            chat = self._require_chat(connection, chat_id)

            if not self._can_access_chat(connection, chat_row=chat, user_id=requester_user_id):
                raise ChatError("forbidden", "User has no access to this chat", 403)
            return self._row_to_chat(chat)

    def get_chat_view(self, *, chat_id: int, requester_user_id: int) -> dict[str, object]:
        """Chat plus the requester's own state (role, posting rights, counters)."""
        with self._connect() as connection:
            self._require_active_user(connection, requester_user_id)
            chat = self._require_chat(connection, chat_id)

            if not self._can_access_chat(connection, chat_row=chat, user_id=requester_user_id):
                raise ChatError("forbidden", "User has no access to this chat", 403)

            role = self._member_role_value(connection, chat_id=chat_id, user_id=requester_user_id)
            member_row = connection.execute(
                "SELECT * FROM chat_members WHERE chat_id = ? AND user_id = ?",
                (chat_id, requester_user_id),
            ).fetchone()
            count_row = connection.execute(
                "SELECT COUNT(*) AS n FROM chat_members WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
            pending_row = connection.execute(
                "SELECT COUNT(*) AS n FROM chat_join_requests WHERE chat_id = ? AND status = 'pending'",
                (chat_id,),
            ).fetchone()

            pinned_message: dict[str, object] | None = None
            pinned_id = self._row_optional_int_lenient(chat, "pinned_message_id")
            if pinned_id:
                pinned_row = self._select_message_row(connection, pinned_id)
                if pinned_row is not None and int(pinned_row["chat_id"]) == chat_id:
                    pinned_message = {
                        "message_id": int(pinned_row["id"]),
                        "author_login": self._row_optional_str_lenient(pinned_row, "author_login"),
                        "body_text": str(pinned_row["body_text"] or "")[:300],
                        "created_at_ms": int(pinned_row["created_at_ms"]),
                    }

            return {
                "chat": self._row_to_chat(chat),
                "my_role": role,
                "is_member": role is not None,
                "is_owner": self._is_chat_owner(connection, chat_row=chat, user_id=requester_user_id),
                "can_post": self._can_post(connection, chat_row=chat, user_id=requester_user_id),
                "member_count": int(count_row["n"]) if count_row is not None else 0,
                "pending_requests": int(pending_row["n"]) if pending_row is not None else 0,
                "pinned_message": pinned_message,
                "draft_text": self._row_optional_str_lenient(member_row, "draft_text") if member_row is not None else None,
                "last_read_message_id": self._row_optional_int_lenient(member_row, "last_read_message_id") if member_row is not None else None,
                "is_muted": self._row_bool(member_row, "is_muted") if member_row is not None else False,
                "is_archived": self._row_bool(member_row, "is_archived") if member_row is not None else False,
                "is_pinned": self._row_bool(member_row, "is_pinned") if member_row is not None else False,
            }

    def update_chat(
        self,
        *,
        chat_id: int,
        actor_user_id: int,
        title: str | None = None,
        description: str | None = None,
        slow_mode_seconds: int | None = None,
        history_visible: bool | None = None,
        is_public: bool | None = None,
        username: str | None = None,
    ) -> ChatRoom:
        with self._connect() as connection:
            actor = self._require_active_user(connection, actor_user_id)
            chat = self._require_chat(connection, chat_id)

            if str(chat["kind"]) != ChatKind.CUSTOM.value:
                raise ChatError("invalid_chat_kind", "Only custom chats can be edited", 409)
            if not self._has_permission(
                connection, chat_row=chat, user_id=actor_user_id, permission="change_info"
            ):
                raise ChatError("forbidden", "Only the owner or an admin can change chat info", 403)

            next_title = str(chat["title"]).strip()
            if title is not None:
                next_title = title.strip()
                if not next_title:
                    raise ChatError("invalid_title", "Chat title must not be empty", 422)

            next_description = (
                (description or "").strip() or None
                if description is not None
                else self._row_optional_str(chat, "description")
            )

            next_slow = int(self._row_optional_int_lenient(chat, "slow_mode_seconds") or 0)
            if slow_mode_seconds is not None:
                next_slow = int(slow_mode_seconds)
                if next_slow < 0 or next_slow > 3600:
                    raise ChatError("invalid_slow_mode", "Slow mode must be between 0 and 3600 seconds", 422)

            next_history = self._row_bool_default(chat, "history_visible", True)
            if history_visible is not None:
                next_history = bool(history_visible)

            next_public = self._row_bool(chat, "is_public")
            if is_public is not None:
                next_public = bool(is_public)

            next_username = self._row_optional_str_lenient(chat, "username")
            if username is not None:
                normalized = self._normalize_username(username)
                if normalized and normalized != next_username:
                    self._require_username_free(connection, username=normalized)
                next_username = normalized
            if not next_public and next_username:
                # a private chat keeps no public link name
                next_username = None

            now_ms = _now_ms()
            connection.execute(
                """
                UPDATE chats
                SET title = ?,
                    description = ?,
                    updated_at_ms = ?,
                    slow_mode_seconds = ?,
                    history_visible = ?,
                    is_public = ?,
                    username = ?
                WHERE id = ?
                """,
                (
                    next_title,
                    next_description,
                    now_ms,
                    next_slow,
                    1 if next_history else 0,
                    1 if next_public else 0,
                    next_username,
                    chat_id,
                ),
            )

            updated = connection.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
            if updated is None:
                raise ChatError("chat_not_found", "Chat not found", 404)
            return self._row_to_chat(updated)

    def set_chat_avatar(self, *, chat_id: int, actor_user_id: int, avatar: AvatarImage) -> ChatRoom:
        normalized_mime = avatar.mime_type.strip().lower()
        extension = _CHAT_AVATAR_EXT_BY_MIME.get(normalized_mime)
        if extension is None:
            raise ChatError("invalid_avatar_mime", "Chat photo must be png, jpeg or webp", 422)
        if len(avatar.content) > MAX_CHAT_AVATAR_BYTES:
            raise ChatError("avatar_too_large", "Chat photo must be <= 2MB", 422)

        with self._connect() as connection:
            actor = self._require_active_user(connection, actor_user_id)
            chat = self._require_chat(connection, chat_id)

            if str(chat["kind"]) != ChatKind.CUSTOM.value:
                raise ChatError("invalid_chat_kind", "Only custom chats can have a photo", 409)
            self._require_chat_manager(connection, chat_row=chat, actor=actor, action="change the chat photo")

            now_ms = _now_ms()
            avatar_name = f"c{chat_id}_{now_ms}_{secrets.token_hex(6)}{extension}"
            root = self._chat_avatars_root()
            root.mkdir(parents=True, exist_ok=True)
            try:
                (root / avatar_name).write_bytes(avatar.content)
            except OSError as exc:
                raise ChatError("avatar_write_failed", "Failed to save chat photo", 500) from exc

            old_path = self._row_optional_str_lenient(chat, "avatar_path")
            connection.execute(
                "UPDATE chats SET avatar_path = ?, updated_at_ms = ? WHERE id = ?",
                (avatar_name, now_ms, chat_id),
            )

            updated = connection.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
            if updated is None:
                raise ChatError("chat_not_found", "Chat not found", 404)
            self._delete_chat_avatar_file(old_path)
            return self._row_to_chat(updated)

    def clear_chat_avatar(self, *, chat_id: int, actor_user_id: int) -> ChatRoom:
        with self._connect() as connection:
            actor = self._require_active_user(connection, actor_user_id)
            chat = self._require_chat(connection, chat_id)

            if str(chat["kind"]) != ChatKind.CUSTOM.value:
                raise ChatError("invalid_chat_kind", "Only custom chats can have a photo", 409)
            self._require_chat_manager(connection, chat_row=chat, actor=actor, action="change the chat photo")

            old_path = self._row_optional_str_lenient(chat, "avatar_path")
            now_ms = _now_ms()
            connection.execute(
                "UPDATE chats SET avatar_path = NULL, updated_at_ms = ? WHERE id = ?",
                (now_ms, chat_id),
            )

            updated = connection.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
            if updated is None:
                raise ChatError("chat_not_found", "Chat not found", 404)
            self._delete_chat_avatar_file(old_path)
            return self._row_to_chat(updated)

    def get_chat_avatar_file(self, *, chat_id: int, requester_user_id: int) -> tuple[Path, str]:
        with self._connect() as connection:
            self._require_active_user(connection, requester_user_id)
            chat = self._require_chat(connection, chat_id)

            if not self._can_access_chat(connection, chat_row=chat, user_id=requester_user_id):
                raise ChatError("forbidden", "User has no access to this chat", 403)

            avatar_name = self._row_optional_str_lenient(chat, "avatar_path")
            if not avatar_name:
                raise ChatError("avatar_not_found", "Chat has no photo", 404)

            file_path = self._chat_avatars_root() / avatar_name
            if not file_path.is_file():
                raise ChatError("avatar_not_found", "Chat photo file is missing", 404)

            mime_type = _CHAT_AVATAR_MIME_BY_EXT.get(file_path.suffix.lower(), "application/octet-stream")
            return file_path, mime_type

    def remove_member(self, *, chat_id: int, target_user_id: int, actor_user_id: int) -> None:
        with self._connect() as connection:
            actor = self._require_active_user(connection, actor_user_id)
            chat = self._require_chat(connection, chat_id)
            target = connection.execute(
                "SELECT * FROM chat_members WHERE chat_id = ? AND user_id = ?",
                (chat_id, target_user_id),
            ).fetchone()
            if target is None:
                raise ChatError("member_not_found", "Member not found", 404)

            if target_user_id == actor_user_id:
                if str(target["role"]) == ChatMemberRole.OWNER.value:
                    raise ChatError(
                        "owner_cannot_leave",
                        "Transfer ownership or delete the chat first",
                        409,
                    )
                connection.execute(
                    "DELETE FROM chat_members WHERE chat_id = ? AND user_id = ?",
                    (chat_id, target_user_id),
                )
                return

            self._require_chat_manager(connection, chat_row=chat, actor=actor, action="remove members")
            if str(target["role"]) == ChatMemberRole.OWNER.value:
                raise ChatError("cannot_remove_owner", "The chat owner cannot be removed", 409)

            actor_id = self._row_int(actor, "id")
            if (
                str(target["role"]) == ChatMemberRole.ADMIN.value
                and not self._is_chat_owner(connection, chat_row=chat, user_id=actor_id)
                and not self._is_platform_moderator(connection, user_id=actor_id)
            ):
                raise ChatError("forbidden", "Only the owner can remove an admin", 403)

            connection.execute(
                "DELETE FROM chat_members WHERE chat_id = ? AND user_id = ?",
                (chat_id, target_user_id),
            )

    def leave_chat(self, *, chat_id: int, user_id: int) -> None:
        self.remove_member(chat_id=chat_id, target_user_id=user_id, actor_user_id=user_id)

    def delete_chat_room(self, *, chat_id: int, actor_user_id: int) -> None:
        with self._connect() as connection:
            actor = self._require_active_user(connection, actor_user_id)
            chat = self._require_chat(connection, chat_id)

            if str(chat["kind"]) == ChatKind.COMMON.value:
                raise ChatError("common_chat_protected", "The general chat cannot be deleted", 409)

            is_manager = self._is_chat_manager(connection, chat_row=chat, actor=actor)
            member = connection.execute(
                "SELECT 1 FROM chat_members WHERE chat_id = ? AND user_id = ?",
                (chat_id, actor_user_id),
            ).fetchone()
            may_delete_dialog = member is not None and self._is_private_dialog(connection, chat)

            if not (is_manager or may_delete_dialog):
                raise ChatError(
                    "forbidden",
                    "Only the owner or an admin can delete this chat",
                    403,
                )

            self._delete_chat_data(connection, chat_id)

    def transfer_owner(self, *, chat_id: int, actor_user_id: int, target_user_id: int) -> ChatRoom:
        with self._connect() as connection:
            actor = self._require_active_user(connection, actor_user_id)
            chat = self._require_chat(connection, chat_id)

            if str(chat["kind"]) != ChatKind.CUSTOM.value:
                raise ChatError("invalid_chat_kind", "Ownership is transferred only in custom chats", 409)
            self._require_chat_manager(connection, chat_row=chat, actor=actor, action="transfer ownership")

            target = connection.execute(
                "SELECT * FROM chat_members WHERE chat_id = ? AND user_id = ?",
                (chat_id, target_user_id),
            ).fetchone()
            if target is None:
                raise ChatError("member_not_found", "The new owner must be a chat member", 404)
            if self._row_optional_int(chat, "owner_user_id") == target_user_id:
                raise ChatError("same_owner", "This user is already the chat owner", 409)

            now_ms = _now_ms()
            connection.execute(
                "UPDATE chats SET owner_user_id = ?, updated_at_ms = ? WHERE id = ?",
                (target_user_id, now_ms, chat_id),
            )
            connection.execute(
                "UPDATE chat_members SET role = ? WHERE chat_id = ? AND user_id = ?",
                (ChatMemberRole.OWNER.value, chat_id, target_user_id),
            )
            connection.execute(
                "UPDATE chat_members SET role = ? WHERE chat_id = ? AND user_id = ? AND role = ?",
                (ChatMemberRole.MEMBER.value, chat_id, actor_user_id, ChatMemberRole.OWNER.value),
            )

            updated = connection.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
            if updated is None:
                raise ChatError("chat_not_found", "Chat not found", 404)
            return self._row_to_chat(updated)

    def set_member_role(
        self,
        *,
        chat_id: int,
        target_user_id: int,
        actor_user_id: int,
        role: ChatMemberRole,
    ) -> ChatMember:
        with self._connect() as connection:
            actor = self._require_active_user(connection, actor_user_id)
            chat = self._require_chat(connection, chat_id)

            if str(chat["kind"]) != ChatKind.CUSTOM.value:
                raise ChatError("invalid_chat_kind", "Roles are managed only in custom chats", 409)
            self._require_chat_manager(connection, chat_row=chat, actor=actor, action="change member roles")

            if role == ChatMemberRole.OWNER:
                raise ChatError("invalid_role", "Use ownership transfer to change the owner", 422)

            target = connection.execute(
                "SELECT * FROM chat_members WHERE chat_id = ? AND user_id = ?",
                (chat_id, target_user_id),
            ).fetchone()
            if target is None:
                raise ChatError("member_not_found", "Member not found", 404)
            if str(target["role"]) == ChatMemberRole.OWNER.value:
                raise ChatError("cannot_change_owner", "The owner role cannot be changed", 409)

            actor_id = self._row_int(actor, "id")
            is_owner = self._row_optional_int(chat, "owner_user_id") == actor_id or self._is_owner(
                connection, chat_id=chat_id, user_id=actor_id
            )
            if (
                not is_owner
                and str(target["role"]) == ChatMemberRole.ADMIN.value
                and role != ChatMemberRole.ADMIN
            ):
                raise ChatError("forbidden", "Only the owner can demote an admin", 403)

            permissions = self._row_optional_str_lenient(target, "permissions")
            if role == ChatMemberRole.ADMIN:
                if not permissions:
                    permissions = json.dumps(default_admin_permissions())
            else:
                permissions = None

            connection.execute(
                "UPDATE chat_members SET role = ?, permissions = ? WHERE chat_id = ? AND user_id = ?",
                (role.value, permissions, chat_id, target_user_id),
            )
            row = connection.execute(
                "SELECT * FROM chat_members WHERE chat_id = ? AND user_id = ?",
                (chat_id, target_user_id),
            ).fetchone()
            if row is None:
                raise ChatError("member_not_found", "Member not found", 404)
            return self._row_to_member(row)

    def set_member_permissions(
        self,
        *,
        chat_id: int,
        target_user_id: int,
        actor_user_id: int,
        permissions: dict[str, bool],
    ) -> ChatMember:
        with self._connect() as connection:
            actor = self._require_active_user(connection, actor_user_id)
            chat = self._require_chat(connection, chat_id)

            if str(chat["kind"]) != ChatKind.CUSTOM.value:
                raise ChatError("invalid_chat_kind", "Permissions are managed only in custom chats", 409)
            self._require_chat_manager(connection, chat_row=chat, actor=actor, action="change admin rights")

            target = connection.execute(
                "SELECT * FROM chat_members WHERE chat_id = ? AND user_id = ?",
                (chat_id, target_user_id),
            ).fetchone()
            if target is None:
                raise ChatError("member_not_found", "Member not found", 404)
            if str(target["role"]) != ChatMemberRole.ADMIN.value:
                raise ChatError("not_an_admin", "Permissions are available for admins only", 409)

            cleaned = {
                name: bool(permissions.get(name, True))
                for name in CHAT_PERMISSIONS
            }
            connection.execute(
                "UPDATE chat_members SET permissions = ? WHERE chat_id = ? AND user_id = ?",
                (json.dumps(cleaned), chat_id, target_user_id),
            )
            row = connection.execute(
                "SELECT * FROM chat_members WHERE chat_id = ? AND user_id = ?",
                (chat_id, target_user_id),
            ).fetchone()
            if row is None:
                raise ChatError("member_not_found", "Member not found", 404)
            return self._row_to_member(row)

    def create_invite(
        self,
        *,
        chat_id: int,
        actor_user_id: int,
        expires_in_hours: int | None = None,
        max_uses: int | None = None,
        requires_approval: bool = False,
    ) -> ChatInvite:
        with self._connect() as connection:
            actor = self._require_active_user(connection, actor_user_id)
            chat = self._require_chat(connection, chat_id)

            if str(chat["kind"]) != ChatKind.CUSTOM.value:
                raise ChatError("invalid_chat_kind", "Invites are available only for custom chats", 409)
            self._require_chat_manager(connection, chat_row=chat, actor=actor, action="manage invites")

            now_ms = _now_ms()
            expires_at_ms = None
            if expires_in_hours:
                hours = int(expires_in_hours)
                if hours <= 0 or hours > 24 * 365:
                    raise ChatError("invalid_expiry", "Invite expiry must be between 1 hour and 1 year", 422)
                expires_at_ms = now_ms + hours * 3600_000

            max_uses_value = None
            if max_uses:
                max_uses_value = int(max_uses)
                if max_uses_value <= 0:
                    raise ChatError("invalid_max_uses", "max_uses must be positive", 422)

            code = ""
            for _ in range(6):
                candidate = self._generate_invite_code()
                if connection.execute("SELECT 1 FROM chat_invites WHERE code = ?", (candidate,)).fetchone() is None:
                    code = candidate
                    break
            if not code:
                raise ChatError("invite_create_failed", "Failed to allocate an invite code", 500)

            cursor = connection.execute(
                """
                INSERT INTO chat_invites(
                    chat_id, code, created_by, created_at_ms, expires_at_ms, max_uses, uses, requires_approval
                )
                VALUES (?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    chat_id,
                    code,
                    actor_user_id,
                    now_ms,
                    expires_at_ms,
                    max_uses_value,
                    1 if requires_approval else 0,
                ),
            )
            invite_id = self._lastrowid(cursor)
            row = connection.execute("SELECT * FROM chat_invites WHERE id = ?", (invite_id,)).fetchone()
            if row is None:
                raise ChatError("invite_create_failed", "Failed to create an invite", 500)
            return self._row_to_invite(row)

    def list_invites(self, *, chat_id: int, actor_user_id: int) -> list[ChatInvite]:
        with self._connect() as connection:
            actor = self._require_active_user(connection, actor_user_id)
            chat = self._require_chat(connection, chat_id)
            self._require_chat_manager(connection, chat_row=chat, actor=actor, action="manage invites")

            rows = connection.execute(
                "SELECT * FROM chat_invites WHERE chat_id = ? ORDER BY created_at_ms DESC, id DESC",
                (chat_id,),
            ).fetchall()
            return [self._row_to_invite(row) for row in rows]

    def revoke_invite(self, *, chat_id: int, invite_id: int, actor_user_id: int) -> None:
        with self._connect() as connection:
            actor = self._require_active_user(connection, actor_user_id)
            chat = self._require_chat(connection, chat_id)
            self._require_chat_manager(connection, chat_row=chat, actor=actor, action="manage invites")

            row = connection.execute(
                "SELECT * FROM chat_invites WHERE id = ? AND chat_id = ?",
                (invite_id, chat_id),
            ).fetchone()
            if row is None:
                raise ChatError("invite_not_found", "Invite not found", 404)
            connection.execute("DELETE FROM chat_invites WHERE id = ?", (invite_id,))

    def join_by_invite_code(self, *, code: str, user_id: int) -> dict[str, object]:
        normalized = (code or "").strip()
        if not normalized:
            raise ChatError("invite_not_found", "Invite link is invalid", 404)

        with self._connect() as connection:
            self._require_active_user(connection, user_id)
            row = connection.execute(
                "SELECT * FROM chat_invites WHERE code = ?",
                (normalized,),
            ).fetchone()
            if row is None:
                raise ChatError("invite_not_found", "Invite link is invalid", 404)

            invite = self._row_to_invite(row)
            now_ms = _now_ms()
            if invite.expires_at_ms is not None and invite.expires_at_ms < now_ms:
                raise ChatError("invite_expired", "Invite link has expired", 410)
            if invite.max_uses is not None and invite.uses >= invite.max_uses:
                raise ChatError("invite_exhausted", "Invite link has reached its limit", 410)

            chat = self._require_chat(connection, invite.chat_id)
            if str(chat["kind"]) != ChatKind.CUSTOM.value:
                raise ChatError("invalid_chat_kind", "Cannot join this chat", 409)

            existing = connection.execute(
                "SELECT 1 FROM chat_members WHERE chat_id = ? AND user_id = ?",
                (invite.chat_id, user_id),
            ).fetchone()
            if existing is not None:
                return {"status": "joined", "chat": self._row_to_chat(chat), "already_member": True}

            if invite.requires_approval:
                self._upsert_join_request(connection, chat_id=invite.chat_id, user_id=user_id, now_ms=now_ms)
                return {"status": "pending", "chat": self._row_to_chat(chat)}

            connection.execute(
                """
                INSERT OR IGNORE INTO chat_members(chat_id, user_id, role, joined_at_ms)
                VALUES (?, ?, ?, ?)
                """,
                (invite.chat_id, user_id, self._default_member_role(chat), now_ms),
            )
            connection.execute("UPDATE chat_invites SET uses = uses + 1 WHERE id = ?", (invite.invite_id,))
            return {"status": "joined", "chat": self._row_to_chat(chat)}

    def join_public_chat(
        self,
        *,
        user_id: int,
        username: str | None = None,
        chat_id: int | None = None,
    ) -> dict[str, object]:
        normalized = self._normalize_username(username) if username else None
        if not normalized and not chat_id:
            raise ChatError("chat_not_found", "Chat not found", 404)

        with self._connect() as connection:
            self._require_active_user(connection, user_id)
            if chat_id:
                row = connection.execute(
                    "SELECT * FROM chats WHERE id = ? AND is_public = 1",
                    (int(chat_id),),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT * FROM chats WHERE username = ? AND is_public = 1",
                    (normalized,),
                ).fetchone()
            if row is None:
                raise ChatError("chat_not_found", "Chat not found", 404)

            existing = connection.execute(
                "SELECT 1 FROM chat_members WHERE chat_id = ? AND user_id = ?",
                (self._row_int(row, "id"), user_id),
            ).fetchone()
            if existing is not None:
                return {"status": "joined", "chat": self._row_to_chat(row), "already_member": True}

            now_ms = _now_ms()
            connection.execute(
                """
                INSERT OR IGNORE INTO chat_members(chat_id, user_id, role, joined_at_ms)
                VALUES (?, ?, ?, ?)
                """,
                (self._row_int(row, "id"), user_id, self._default_member_role(row), now_ms),
            )
            return {"status": "joined", "chat": self._row_to_chat(row)}

    def search_public_chats(
        self,
        *,
        user_id: int,
        query: str,
        limit: int = 10,
    ) -> list[ChatRoom]:
        """Public joinable chats matching a name, excluding chats the user is already in."""
        needle = (query or "").strip().casefold()
        if len(needle) < 2:
            return []

        safe_limit = min(max(int(limit), 1), 50)
        with self._connect() as connection:
            self._require_active_user(connection, user_id)
            rows = connection.execute(
                """
                SELECT c.*
                FROM chats c
                WHERE c.is_public = 1
                  AND NOT EXISTS (
                      SELECT 1 FROM chat_members m
                      WHERE m.chat_id = c.id AND m.user_id = ?
                  )
                ORDER BY c.updated_at_ms DESC
                LIMIT 300
                """,
                (user_id,),
            ).fetchall()

        # SQLite's LIKE is ASCII-only for case folding, so match in Python to
        # support Cyrillic names.
        matches: list[ChatRoom] = []
        for row in rows:
            title = self._row_optional_str_lenient(row, "title") or ""
            username = self._row_optional_str_lenient(row, "username") or ""
            if needle in title.casefold() or needle in username.casefold():
                matches.append(self._row_to_chat(row))
            if len(matches) >= safe_limit:
                break
        return matches

    def list_join_requests(self, *, chat_id: int, actor_user_id: int) -> list[dict[str, object]]:
        with self._connect() as connection:
            actor = self._require_active_user(connection, actor_user_id)
            chat = self._require_chat(connection, chat_id)
            self._require_chat_manager(connection, chat_row=chat, actor=actor, action="manage join requests")

            rows = connection.execute(
                """
                SELECT r.*, u.login AS login, u.avatar_emoji AS avatar_emoji,
                       u.avatar_path AS avatar_path, u.avatar_updated_at_ms AS avatar_updated_at_ms
                FROM chat_join_requests r
                LEFT JOIN users u ON u.id = r.user_id
                WHERE r.chat_id = ? AND r.status = 'pending'
                ORDER BY r.created_at_ms ASC
                """,
                (chat_id,),
            ).fetchall()
            items: list[dict[str, object]] = []
            for row in rows:
                items.append(
                    {
                        "user_id": int(row["user_id"]),
                        "status": str(row["status"]),
                        "created_at_ms": int(row["created_at_ms"]),
                        "login": self._row_optional_str_lenient(row, "login") or f"user#{int(row['user_id'])}",
                        "avatar_emoji": self._row_optional_str_lenient(row, "avatar_emoji"),
                        "has_avatar": bool(self._row_optional_str_lenient(row, "avatar_path")),
                        "avatar_updated_at_ms": self._row_optional_int_lenient(row, "avatar_updated_at_ms"),
                    }
                )
            return items

    def decide_join_request(
        self,
        *,
        chat_id: int,
        target_user_id: int,
        actor_user_id: int,
        approve: bool,
    ) -> ChatJoinRequest:
        with self._connect() as connection:
            actor = self._require_active_user(connection, actor_user_id)
            chat = self._require_chat(connection, chat_id)
            self._require_chat_manager(connection, chat_row=chat, actor=actor, action="manage join requests")

            row = connection.execute(
                "SELECT * FROM chat_join_requests WHERE chat_id = ? AND user_id = ?",
                (chat_id, target_user_id),
            ).fetchone()
            if row is None:
                raise ChatError("request_not_found", "Join request not found", 404)
            if str(row["status"]) != "pending":
                raise ChatError("request_already_decided", "Join request was already decided", 409)

            now_ms = _now_ms()
            if approve:
                self._require_active_user(connection, target_user_id)
                connection.execute(
                    """
                    INSERT OR IGNORE INTO chat_members(chat_id, user_id, role, joined_at_ms)
                    VALUES (?, ?, ?, ?)
                    """,
                    (chat_id, target_user_id, self._default_member_role(chat), now_ms),
                )
                status = "approved"
            else:
                status = "declined"

            connection.execute(
                "UPDATE chat_join_requests SET status = ?, decided_by = ?, decided_at_ms = ? WHERE chat_id = ? AND user_id = ?",
                (status, actor_user_id, now_ms, chat_id, target_user_id),
            )
            updated = connection.execute(
                "SELECT * FROM chat_join_requests WHERE chat_id = ? AND user_id = ?",
                (chat_id, target_user_id),
            ).fetchone()
            if updated is None:
                raise ChatError("request_not_found", "Join request not found", 404)
            return self._row_to_join_request(updated)

    def set_pinned_message(
        self,
        *,
        chat_id: int,
        actor_user_id: int,
        message_id: int | None,
    ) -> ChatRoom:
        with self._connect() as connection:
            actor = self._require_active_user(connection, actor_user_id)
            chat = self._require_chat(connection, chat_id)

            if not self._has_permission(connection, chat_row=chat, user_id=actor_user_id, permission="pin_messages"):
                raise ChatError("forbidden", "Only the owner or an admin can pin messages", 403)

            if message_id is not None:
                row = connection.execute(
                    "SELECT 1 FROM chat_messages WHERE id = ? AND chat_id = ?",
                    (message_id, chat_id),
                ).fetchone()
                if row is None:
                    raise ChatError("message_not_found", "Message not found", 404)

            now_ms = _now_ms()
            connection.execute(
                "UPDATE chats SET pinned_message_id = ?, updated_at_ms = ? WHERE id = ?",
                (message_id, now_ms, chat_id),
            )
            updated = connection.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
            if updated is None:
                raise ChatError("chat_not_found", "Chat not found", 404)
            return self._row_to_chat(updated)

    def toggle_reaction(
        self,
        *,
        chat_id: int,
        message_id: int,
        user_id: int,
        emoji: str,
    ) -> ChatMessage:
        normalized = (emoji or "").strip()
        if normalized not in REACTION_EMOJIS:
            raise ChatError("invalid_reaction", "Unsupported reaction", 422)

        with self._connect() as connection:
            self._require_active_user(connection, user_id)
            chat = self._require_chat(connection, chat_id)
            if not self._can_access_chat(connection, chat_row=chat, user_id=user_id):
                raise ChatError("forbidden", "User has no access to this chat", 403)

            row = connection.execute(
                "SELECT id FROM chat_messages WHERE id = ? AND chat_id = ?",
                (message_id, chat_id),
            ).fetchone()
            if row is None:
                raise ChatError("message_not_found", "Message not found", 404)

            existing = connection.execute(
                "SELECT 1 FROM chat_message_reactions WHERE message_id = ? AND user_id = ? AND emoji = ?",
                (message_id, user_id, normalized),
            ).fetchone()
            if existing is not None:
                connection.execute(
                    "DELETE FROM chat_message_reactions WHERE message_id = ? AND user_id = ? AND emoji = ?",
                    (message_id, user_id, normalized),
                )
            else:
                # one reaction per user per message (Telegram-like quick reactions)
                connection.execute(
                    "DELETE FROM chat_message_reactions WHERE message_id = ? AND user_id = ?",
                    (message_id, user_id),
                )
                connection.execute(
                    """
                    INSERT OR REPLACE INTO chat_message_reactions(message_id, user_id, emoji, created_at_ms)
                    VALUES (?, ?, ?, ?)
                    """,
                    (message_id, user_id, normalized, _now_ms()),
                )

            message_row = self._select_message_row(connection, message_id)
            if message_row is None:
                raise ChatError("message_not_found", "Message not found", 404)
            reactions = self._reactions_for_messages(connection, [message_id], viewer_user_id=user_id)
            return self._with_message_attachments(
                connection,
                self._row_to_message(message_row),
                reactions_by_id=reactions,
            )

    def forward_message(
        self,
        *,
        source_chat_id: int,
        message_id: int,
        target_chat_id: int,
        actor_user_id: int,
    ) -> ChatMessage:
        with self._connect() as connection:
            self._require_active_user(connection, actor_user_id)
            source_chat = self._require_chat(connection, source_chat_id)
            if not self._can_access_chat(connection, chat_row=source_chat, user_id=actor_user_id):
                raise ChatError("forbidden", "User has no access to the source chat", 403)

            source_row = self._select_message_row(connection, message_id)
            if source_row is None or int(source_row["chat_id"]) != source_chat_id:
                raise ChatError("message_not_found", "Message not found", 404)

            target_chat = self._require_chat(connection, target_chat_id)
            if not self._can_access_chat(connection, chat_row=target_chat, user_id=actor_user_id):
                raise ChatError("forbidden", "User has no access to the target chat", 403)
            if not self._can_post(connection, chat_row=target_chat, user_id=actor_user_id):
                raise ChatError("read_only", "Only admins can post in this chat", 403)

            now_ms = _now_ms()
            cursor = connection.execute(
                """
                INSERT INTO chat_messages(
                    chat_id, author_user_id, body_text, client_message_id, created_at_ms, edited_at_ms,
                    forwarded_from_chat_id, forwarded_from_message_id, forwarded_from_user_id, forwarded_from_login
                )
                VALUES (?, ?, ?, NULL, ?, NULL, ?, ?, ?, ?)
                """,
                (
                    target_chat_id,
                    actor_user_id,
                    str(source_row["body_text"] or ""),
                    now_ms,
                    source_chat_id,
                    message_id,
                    int(source_row["author_user_id"]),
                    self._row_optional_str_lenient(source_row, "author_login"),
                ),
            )
            new_message_id = self._lastrowid(cursor)
            connection.execute(
                """
                INSERT OR IGNORE INTO chat_message_attachments(message_id, attachment_id, position)
                SELECT ?, attachment_id, position FROM chat_message_attachments WHERE message_id = ?
                """,
                (new_message_id, message_id),
            )
            connection.execute(
                "UPDATE chats SET updated_at_ms = ? WHERE id = ?",
                (now_ms, target_chat_id),
            )

            row = self._select_message_row(connection, new_message_id)
            if row is None:
                raise ChatError("message_create_failed", "Failed to forward the message", 500)
            return self._with_message_attachments(connection, self._row_to_message(row))

    def mark_read(self, *, chat_id: int, user_id: int, message_id: int) -> None:
        with self._connect() as connection:
            self._require_active_user(connection, user_id)
            row = connection.execute(
                "SELECT last_read_message_id FROM chat_members WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id),
            ).fetchone()
            if row is None:
                # Common (server-wide) chats have no membership rows, so the read marker
                # had nowhere to go and the unread badge could never be cleared.
                # Create the row lazily: joined_at_ms = 0 keeps history fully visible,
                # exactly as it was while there was no membership row.
                chat_row = connection.execute(
                    "SELECT kind FROM chats WHERE id = ?",
                    (chat_id,),
                ).fetchone()
                if chat_row is None or str(chat_row["kind"]) != ChatKind.COMMON.value:
                    return
                connection.execute(
                    """
                    INSERT OR IGNORE INTO chat_members(
                        chat_id,
                        user_id,
                        role,
                        joined_at_ms,
                        last_read_message_id
                    )
                    VALUES (?, ?, 'member', 0, ?)
                    """,
                    (chat_id, user_id, max(int(message_id), 0)),
                )
                return
            current = self._row_optional_int_lenient(row, "last_read_message_id") or 0
            if int(message_id) > current:
                connection.execute(
                    "UPDATE chat_members SET last_read_message_id = ? WHERE chat_id = ? AND user_id = ?",
                    (int(message_id), chat_id, user_id),
                )

    def save_draft(self, *, chat_id: int, user_id: int, text: str) -> None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM chat_members WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id),
            ).fetchone()
            if row is None:
                return
            cleaned = (text or "").strip()
            connection.execute(
                "UPDATE chat_members SET draft_text = ?, draft_updated_at_ms = ? WHERE chat_id = ? AND user_id = ?",
                (cleaned or None, _now_ms(), chat_id, user_id),
            )

    def set_chat_user_state(
        self,
        *,
        chat_id: int,
        user_id: int,
        is_muted: bool | None = None,
        is_archived: bool | None = None,
        is_pinned: bool | None = None,
    ) -> dict[str, object]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM chat_members WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id),
            ).fetchone()
            if row is None:
                raise ChatError("member_not_found", "You are not a member of this chat", 404)

            next_muted = self._row_bool(row, "is_muted") if is_muted is None else bool(is_muted)
            next_archived = self._row_bool(row, "is_archived") if is_archived is None else bool(is_archived)
            next_pinned = self._row_bool(row, "is_pinned") if is_pinned is None else bool(is_pinned)

            connection.execute(
                "UPDATE chat_members SET is_muted = ?, is_archived = ?, is_pinned = ? WHERE chat_id = ? AND user_id = ?",
                (1 if next_muted else 0, 1 if next_archived else 0, 1 if next_pinned else 0, chat_id, user_id),
            )
            return {"is_muted": next_muted, "is_archived": next_archived, "is_pinned": next_pinned}

    def clear_history_for_user(self, *, chat_id: int, user_id: int) -> None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM chat_members WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id),
            ).fetchone()
            if row is None:
                raise ChatError("member_not_found", "You are not a member of this chat", 404)
            connection.execute(
                "UPDATE chat_members SET cleared_at_ms = ? WHERE chat_id = ? AND user_id = ?",
                (_now_ms(), chat_id, user_id),
            )

    def search_messages(
        self,
        *,
        user_id: int,
        query: str,
        chat_id: int | None = None,
        limit: int = 50,
    ) -> list[dict[str, object]]:
        safe_limit = min(max(int(limit), 1), 100)
        needle = (query or "").strip()
        if not needle:
            return []

        with self._connect() as connection:
            self._require_active_user(connection, user_id)
            params: list[object] = [user_id, f"%{needle}%", user_id]
            chat_filter = ""
            if chat_id is not None:
                chat_filter = " AND c.id = ? "
                params.append(int(chat_id))
            params.append(safe_limit)

            rows = connection.execute(
                f"""
                SELECT m.id AS message_id,
                       m.chat_id AS chat_id,
                       c.title AS chat_title,
                       m.author_user_id AS author_user_id,
                       u.login AS author_login,
                       m.body_text AS body_text,
                       m.created_at_ms AS created_at_ms
                FROM chat_messages m
                JOIN chats c ON c.id = m.chat_id
                LEFT JOIN users u ON u.id = m.author_user_id
                LEFT JOIN chat_members cm ON cm.chat_id = c.id AND cm.user_id = ?
                WHERE m.body_text LIKE ?
                  AND (
                        c.kind = 'common'
                     OR c.is_public = 1
                     OR cm.user_id IS NOT NULL
                     OR EXISTS (SELECT 1 FROM users a WHERE a.id = ? AND a.role IN ('admin','moderator'))
                  )
                  AND m.created_at_ms >= COALESCE(cm.cleared_at_ms, 0)
                  AND (c.history_visible = 1 OR m.created_at_ms >= COALESCE(cm.joined_at_ms, 0))
                  {chat_filter}
                ORDER BY m.created_at_ms DESC, m.id DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
            return [dict(row) for row in rows]

    def list_chat_summaries(self, *, user_id: int) -> list[dict[str, object]]:
        """Chats of the user with unread counters, drafts and per-user flags."""
        with self._connect() as connection:
            self._require_active_user(connection, user_id)
            rows = connection.execute(
                """
                SELECT c.*,
                       m.role AS member_role,
                       m.is_muted AS is_muted,
                       m.is_archived AS is_archived,
                       m.is_pinned AS is_pinned,
                       m.last_read_message_id AS last_read_message_id,
                       m.cleared_at_ms AS cleared_at_ms,
                       m.joined_at_ms AS joined_at_ms,
                       m.draft_text AS draft_text,
                       m.draft_updated_at_ms AS draft_updated_at_ms,
                       (
                           SELECT COUNT(*)
                           FROM chat_messages msg
                           WHERE msg.chat_id = c.id
                             AND msg.author_user_id != ?
                             AND msg.id > COALESCE(m.last_read_message_id, 0)
                             AND msg.created_at_ms >= COALESCE(m.cleared_at_ms, 0)
                             AND (c.history_visible = 1 OR msg.created_at_ms >= COALESCE(m.joined_at_ms, 0))
                       ) AS unread_count,
                       (
                           SELECT msg.body_text
                           FROM chat_messages msg
                           WHERE msg.chat_id = c.id
                             AND msg.created_at_ms >= COALESCE(m.cleared_at_ms, 0)
                           ORDER BY msg.created_at_ms DESC, msg.id DESC
                           LIMIT 1
                       ) AS last_message_text,
                       (
                           SELECT msg.created_at_ms
                           FROM chat_messages msg
                           WHERE msg.chat_id = c.id
                             AND msg.created_at_ms >= COALESCE(m.cleared_at_ms, 0)
                           ORDER BY msg.created_at_ms DESC, msg.id DESC
                           LIMIT 1
                       ) AS last_message_at_ms
                FROM chats c
                LEFT JOIN chat_members m ON m.chat_id = c.id AND m.user_id = ?
                WHERE c.kind = 'common' OR m.user_id IS NOT NULL
                ORDER BY COALESCE(m.is_pinned, 0) DESC, c.updated_at_ms DESC, c.id DESC
                """,
                (user_id, user_id),
            ).fetchall()

            summaries: list[dict[str, object]] = []
            for row in rows:
                summaries.append(
                    {
                        "chat": self._row_to_chat(row),
                        "my_role": self._row_optional_str_lenient(row, "member_role"),
                        "is_member": self._row_optional_str_lenient(row, "member_role") is not None,
                        "is_muted": self._row_bool(row, "is_muted"),
                        "is_archived": self._row_bool(row, "is_archived"),
                        "is_pinned": self._row_bool(row, "is_pinned"),
                        "unread_count": int(self._row_optional_int_lenient(row, "unread_count") or 0),
                        "draft_text": self._row_optional_str_lenient(row, "draft_text"),
                        "draft_updated_at_ms": self._row_optional_int_lenient(row, "draft_updated_at_ms"),
                        "last_message_text": self._row_optional_str_lenient(row, "last_message_text"),
                        "last_message_at_ms": self._row_optional_int_lenient(row, "last_message_at_ms"),
                    }
                )
            return summaries

    def create_poll(
        self,
        *,
        chat_id: int,
        author_user_id: int,
        question: str,
        options: Sequence[str],
        is_multiple: bool = False,
        is_anonymous: bool = False,
    ) -> ChatMessage:
        cleaned_question = (question or "").strip()
        if not cleaned_question:
            raise ChatError("invalid_poll", "Poll question must not be empty", 422)
        cleaned_options = [(option or "").strip() for option in options]
        cleaned_options = [option for option in cleaned_options if option]
        if len(cleaned_options) < 2 or len(cleaned_options) > 10:
            raise ChatError("invalid_poll", "A poll needs 2 to 10 options", 422)

        with self._connect() as connection:
            self._require_active_user(connection, author_user_id)
            chat = self._require_chat(connection, chat_id)
            if not self._can_access_chat(connection, chat_row=chat, user_id=author_user_id):
                raise ChatError("forbidden", "User has no access to this chat", 403)
            if not self._can_post(connection, chat_row=chat, user_id=author_user_id):
                raise ChatError("read_only", "Only admins can post in this chat", 403)
            self._enforce_slow_mode(connection, chat_row=chat, user_id=author_user_id)

            now_ms = _now_ms()
            cursor = connection.execute(
                """
                INSERT INTO chat_messages(
                    chat_id, author_user_id, body_text, client_message_id, created_at_ms, edited_at_ms
                )
                VALUES (?, ?, ?, NULL, ?, NULL)
                """,
                (chat_id, author_user_id, cleaned_question, now_ms),
            )
            message_id = self._lastrowid(cursor)
            connection.execute(
                """
                INSERT INTO chat_polls(
                    chat_id, message_id, created_by, question, options_json,
                    is_multiple, is_anonymous, created_at_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chat_id,
                    message_id,
                    author_user_id,
                    cleaned_question,
                    json.dumps(cleaned_options, ensure_ascii=False),
                    1 if is_multiple else 0,
                    1 if is_anonymous else 0,
                    now_ms,
                ),
            )
            connection.execute("UPDATE chats SET updated_at_ms = ? WHERE id = ?", (now_ms, chat_id))

            row = self._select_message_row(connection, message_id)
            if row is None:
                raise ChatError("poll_create_failed", "Failed to create the poll", 500)
            polls = self._polls_for_messages(connection, [message_id], viewer_user_id=author_user_id)
            return self._with_message_attachments(
                connection,
                self._row_to_message(row),
                polls_by_id=polls,
            )

    def vote_poll(
        self,
        *,
        chat_id: int,
        poll_id: int,
        user_id: int,
        option_index: int,
    ) -> ChatMessage:
        with self._connect() as connection:
            self._require_active_user(connection, user_id)
            chat = self._require_chat(connection, chat_id)
            if not self._can_access_chat(connection, chat_row=chat, user_id=user_id):
                raise ChatError("forbidden", "User has no access to this chat", 403)

            row = connection.execute(
                "SELECT * FROM chat_polls WHERE id = ? AND chat_id = ?",
                (poll_id, chat_id),
            ).fetchone()
            if row is None:
                raise ChatError("poll_not_found", "Poll not found", 404)
            if self._row_optional_int_lenient(row, "closed_at_ms") is not None:
                raise ChatError("poll_closed", "Poll is closed", 409)

            try:
                raw_options = json.loads(str(row["options_json"]))
            except (TypeError, ValueError):
                raw_options = []
            if not isinstance(raw_options, list):
                raw_options = []
            index = int(option_index)
            if index < 0 or index >= len(raw_options):
                raise ChatError("invalid_option", "Unknown poll option", 422)

            if not self._row_bool(row, "is_multiple"):
                connection.execute(
                    "DELETE FROM chat_poll_votes WHERE poll_id = ? AND user_id = ?",
                    (poll_id, user_id),
                )

            existing = connection.execute(
                "SELECT 1 FROM chat_poll_votes WHERE poll_id = ? AND user_id = ? AND option_index = ?",
                (poll_id, user_id, index),
            ).fetchone()
            if existing is not None:
                connection.execute(
                    "DELETE FROM chat_poll_votes WHERE poll_id = ? AND user_id = ? AND option_index = ?",
                    (poll_id, user_id, index),
                )
            else:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO chat_poll_votes(poll_id, user_id, option_index, created_at_ms)
                    VALUES (?, ?, ?, ?)
                    """,
                    (poll_id, user_id, index, _now_ms()),
                )

            message_id = self._row_optional_int_lenient(row, "message_id")
            if message_id is None:
                raise ChatError("poll_message_missing", "Poll has no message", 500)
            message_row = self._select_message_row(connection, message_id)
            if message_row is None:
                raise ChatError("message_not_found", "Message not found", 404)
            polls = self._polls_for_messages(connection, [message_id], viewer_user_id=user_id)
            return self._with_message_attachments(
                connection,
                self._row_to_message(message_row),
                polls_by_id=polls,
            )

    # --- User blocks ---

    def block_user(self, *, blocker_user_id: int, blocked_user_id: int) -> None:
        if blocker_user_id == blocked_user_id:
            raise ChatError("invalid_target", "Cannot block yourself", 400)
        with self._connect() as connection:
            self._require_active_user(connection, blocker_user_id)
            self._require_active_user(connection, blocked_user_id)
            connection.execute(
                """
                INSERT OR IGNORE INTO user_blocks(blocker_user_id, blocked_user_id, created_at_ms)
                VALUES (?, ?, ?)
                """,
                (blocker_user_id, blocked_user_id, _now_ms()),
            )

    def unblock_user(self, *, blocker_user_id: int, blocked_user_id: int) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM user_blocks WHERE blocker_user_id = ? AND blocked_user_id = ?",
                (blocker_user_id, blocked_user_id),
            )

    def list_blocked_user_ids(self, *, user_id: int) -> list[int]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT blocked_user_id FROM user_blocks WHERE blocker_user_id = ? ORDER BY created_at_ms DESC",
                (user_id,),
            ).fetchall()
            return [int(row["blocked_user_id"]) for row in rows]

    def is_blocked_between(self, *, user_a: int, user_b: int) -> bool:
        with self._connect() as connection:
            return self._is_blocked_between(connection, user_a=user_a, user_b=user_b)

    @staticmethod
    def _is_blocked_between(connection: sqlite3.Connection, *, user_a: int, user_b: int) -> bool:
        row = connection.execute(
            """
            SELECT 1 FROM user_blocks
            WHERE (blocker_user_id = ? AND blocked_user_id = ?)
               OR (blocker_user_id = ? AND blocked_user_id = ?)
            LIMIT 1
            """,
            (user_a, user_b, user_b, user_a),
        ).fetchone()
        return row is not None

    def _upsert_join_request(
        self,
        connection: sqlite3.Connection,
        *,
        chat_id: int,
        user_id: int,
        now_ms: int,
    ) -> None:
        connection.execute(
            """
            INSERT INTO chat_join_requests(chat_id, user_id, status, created_at_ms)
            VALUES (?, ?, 'pending', ?)
            ON CONFLICT(chat_id, user_id) DO UPDATE SET
                status = 'pending',
                created_at_ms = excluded.created_at_ms,
                decided_by = NULL,
                decided_at_ms = NULL
            """,
            (chat_id, user_id, now_ms),
        )

    @staticmethod
    def _default_member_role(chat_row: sqlite3.Row) -> str:
        chat_type = ChatService._row_optional_str_lenient(chat_row, "chat_type") or ChatType.GROUP.value
        if chat_type == ChatType.CHANNEL.value:
            return ChatMemberRole.SUBSCRIBER.value
        return ChatMemberRole.MEMBER.value

    @staticmethod
    def _generate_invite_code() -> str:
        return secrets.token_urlsafe(9).replace("-", "").replace("_", "")[:12]

    @staticmethod
    def _normalize_username(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lstrip("@").lower()
        if not normalized:
            return None
        if len(normalized) < 4 or len(normalized) > 32:
            raise ChatError("invalid_username", "Link name must be 4-32 characters long", 422)
        if not all(ch.isalnum() or ch == "_" for ch in normalized):
            raise ChatError("invalid_username", "Link name may contain letters, digits and underscores", 422)
        return normalized

    @staticmethod
    def _require_username_free(connection: sqlite3.Connection, *, username: str) -> None:
        row = connection.execute(
            "SELECT 1 FROM chats WHERE username = ?",
            (username,),
        ).fetchone()
        if row is not None:
            raise ChatError("username_taken", "This link name is already taken", 409)

    def _member_role_value(
        self,
        connection: sqlite3.Connection,
        *,
        chat_id: int,
        user_id: int,
    ) -> str | None:
        row = connection.execute(
            "SELECT role FROM chat_members WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        ).fetchone()
        return str(row["role"]) if row is not None else None

    def _is_platform_moderator(self, connection: sqlite3.Connection, *, user_id: int) -> bool:
        row = connection.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            return False
        return str(row["role"]) in {UserRole.ADMIN.value, UserRole.MODERATOR.value}

    def _is_chat_owner(self, connection: sqlite3.Connection, *, chat_row: sqlite3.Row, user_id: int) -> bool:
        if self._row_optional_int(chat_row, "owner_user_id") == user_id:
            return True
        return self._is_owner(connection, chat_id=self._row_int(chat_row, "id"), user_id=user_id)

    def _has_permission(
        self,
        connection: sqlite3.Connection,
        *,
        chat_row: sqlite3.Row,
        user_id: int,
        permission: str,
    ) -> bool:
        if self._is_platform_moderator(connection, user_id=user_id):
            return True

        chat_id = self._row_int(chat_row, "id")
        role = self._member_role_value(connection, chat_id=chat_id, user_id=user_id)
        if role is None:
            return False
        if role == ChatMemberRole.OWNER.value or self._is_chat_owner(connection, chat_row=chat_row, user_id=user_id):
            return True
        if role != ChatMemberRole.ADMIN.value:
            return False

        row = connection.execute(
            "SELECT permissions FROM chat_members WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        ).fetchone()
        raw = self._row_optional_str_lenient(row, "permissions") if row is not None else None
        if not raw:
            return True
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return True
        if not isinstance(data, dict):
            return True
        return bool(data.get(permission, True))

    def _can_post(
        self,
        connection: sqlite3.Connection,
        *,
        chat_row: sqlite3.Row,
        user_id: int,
    ) -> bool:
        if self._is_platform_moderator(connection, user_id=user_id):
            return True

        chat_id = self._row_int(chat_row, "id")
        role = self._member_role_value(connection, chat_id=chat_id, user_id=user_id)
        if role is None:
            return False

        chat_type = self._row_optional_str_lenient(chat_row, "chat_type") or ChatType.GROUP.value
        if chat_type == ChatType.CHANNEL.value:
            return role in {ChatMemberRole.OWNER.value, ChatMemberRole.ADMIN.value}
        if role == ChatMemberRole.SUBSCRIBER.value:
            return False
        return True

    def _enforce_slow_mode(
        self,
        connection: sqlite3.Connection,
        *,
        chat_row: sqlite3.Row,
        user_id: int,
    ) -> None:
        slow = int(self._row_optional_int_lenient(chat_row, "slow_mode_seconds") or 0)
        if slow <= 0:
            return
        if self._is_platform_moderator(connection, user_id=user_id):
            return

        chat_id = self._row_int(chat_row, "id")
        role = self._member_role_value(connection, chat_id=chat_id, user_id=user_id)
        if role in {ChatMemberRole.OWNER.value, ChatMemberRole.ADMIN.value}:
            return

        row = connection.execute(
            """
            SELECT created_at_ms FROM chat_messages
            WHERE chat_id = ? AND author_user_id = ?
            ORDER BY created_at_ms DESC, id DESC
            LIMIT 1
            """,
            (chat_id, user_id),
        ).fetchone()
        if row is None:
            return

        elapsed_ms = _now_ms() - int(row["created_at_ms"])
        if elapsed_ms < slow * 1000:
            wait_seconds = max(int((slow * 1000 - elapsed_ms + 999) // 1000), 1)
            raise ChatError("slow_mode", f"Slow mode: wait {wait_seconds} s", 429)

    def _chat_avatars_root(self) -> Path:
        return self._storage_root / "chat_avatars"

    def _delete_chat_avatar_file(self, avatar_name: str | None) -> None:
        if not avatar_name:
            return
        try:
            (self._chat_avatars_root() / avatar_name).unlink(missing_ok=True)
        except OSError:
            pass

    def _is_chat_manager(
        self,
        connection: sqlite3.Connection,
        *,
        chat_row: sqlite3.Row,
        actor: sqlite3.Row,
    ) -> bool:
        """Owner, platform admin/moderator or group admin may manage the chat."""
        actor_id = self._row_int(actor, "id")
        if str(actor["role"]) in {UserRole.ADMIN.value, UserRole.MODERATOR.value}:
            return True

        chat_id = self._row_int(chat_row, "id")
        if self._row_optional_int(chat_row, "owner_user_id") == actor_id:
            return True
        if self._is_owner(connection, chat_id=chat_id, user_id=actor_id):
            return True

        member = connection.execute(
            "SELECT role FROM chat_members WHERE chat_id = ? AND user_id = ?",
            (chat_id, actor_id),
        ).fetchone()
        return member is not None and str(member["role"]) == "admin"

    def _require_chat_manager(
        self,
        connection: sqlite3.Connection,
        *,
        chat_row: sqlite3.Row,
        actor: sqlite3.Row,
        action: str = "manage this chat",
    ) -> None:
        if not self._is_chat_manager(connection, chat_row=chat_row, actor=actor):
            raise ChatError("forbidden", f"Only the chat owner or an admin can {action}", 403)

    def _is_private_dialog(self, connection: sqlite3.Connection, chat_row: sqlite3.Row) -> bool:
        """One-on-one private chat (not a private room with a room code)."""
        if str(chat_row["kind"]) != ChatKind.CUSTOM.value:
            return False
        if not self._row_bool(chat_row, "is_private"):
            return False
        if self._row_optional_str_lenient(chat_row, "room_code_hash"):
            return False
        count_row = connection.execute(
            "SELECT COUNT(*) AS n FROM chat_members WHERE chat_id = ?",
            (self._row_int(chat_row, "id"),),
        ).fetchone()
        return count_row is not None and int(count_row["n"]) == 2

    def _delete_chat_data(self, connection: sqlite3.Connection, chat_id: int) -> None:
        row = connection.execute("SELECT avatar_path FROM chats WHERE id = ?", (chat_id,)).fetchone()
        avatar_path = self._row_optional_str_lenient(row, "avatar_path") if row is not None else None

        connection.execute(
            "DELETE FROM chat_message_attachments WHERE message_id IN (SELECT id FROM chat_messages WHERE chat_id = ?)",
            (chat_id,),
        )
        connection.execute("DELETE FROM chat_messages WHERE chat_id = ?", (chat_id,))
        connection.execute("DELETE FROM chat_members WHERE chat_id = ?", (chat_id,))
        connection.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
        self._delete_chat_avatar_file(avatar_path)

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

            if not self._can_post(connection, chat_row=chat, user_id=author_user_id):
                raise ChatError("read_only", "Only admins can post in this chat", 403)

            if self._is_private_dialog(connection, chat) and not self._is_platform_moderator(
                connection, user_id=author_user_id
            ):
                other = connection.execute(
                    "SELECT user_id FROM chat_members WHERE chat_id = ? AND user_id != ? LIMIT 1",
                    (chat_id, author_user_id),
                ).fetchone()
                if other is not None and self._is_blocked_between(
                    connection,
                    user_a=author_user_id,
                    user_b=int(other["user_id"]),
                ):
                    raise ChatError(
                        "blocked",
                        "Messaging is not available: one of the users is blocked",
                        403,
                    )

            self._enforce_slow_mode(connection, chat_row=chat, user_id=author_user_id)

            now_ms = _now_ms()
            text = draft.body_text.strip()
            client_message_id = (draft.client_message_id or "").strip() or None
            attachment_ids = self._normalize_attachment_ids(draft.attachment_ids)

            reply_to_message_id = draft.reply_to_message_id
            if reply_to_message_id is not None:
                parent = connection.execute(
                    "SELECT id FROM chat_messages WHERE id = ? AND chat_id = ?",
                    (int(reply_to_message_id), chat_id),
                ).fetchone()
                if parent is None:
                    raise ChatError("reply_target_not_found", "Replied message was not found", 404)

            try:
                cursor = connection.execute(
                    """
                    INSERT INTO chat_messages(
                        chat_id,
                        author_user_id,
                        body_text,
                        client_message_id,
                        created_at_ms,
                        edited_at_ms,
                        reply_to_message_id
                    )
                    VALUES (?, ?, ?, ?, ?, NULL, ?)
                    """,
                    (chat_id, author_user_id, text, client_message_id, now_ms, reply_to_message_id),
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

            member_row = connection.execute(
                "SELECT joined_at_ms, cleared_at_ms FROM chat_members WHERE chat_id = ? AND user_id = ?",
                (chat_id, requester_user_id),
            ).fetchone()

            # History for new members: everything posted before joining stays hidden.
            min_created_at_ms = 0
            if member_row is not None:
                if not self._row_bool_default(chat, "history_visible", True):
                    min_created_at_ms = int(member_row["joined_at_ms"] or 0)
                cleared_at_ms = self._row_optional_int_lenient(member_row, "cleared_at_ms")
                if cleared_at_ms:
                    min_created_at_ms = max(min_created_at_ms, int(cleared_at_ms))

            rows = connection.execute(
                """
                SELECT m.*,
                       u.login AS author_login,
                       u.avatar_emoji AS author_avatar_emoji,
                       rm.body_text AS reply_text,
                       ru.login AS reply_login
                FROM chat_messages m
                LEFT JOIN users u ON u.id = m.author_user_id
                LEFT JOIN chat_messages rm ON rm.id = m.reply_to_message_id
                LEFT JOIN users ru ON ru.id = rm.author_user_id
                WHERE m.chat_id = ?
                  AND m.created_at_ms >= ?
                ORDER BY m.created_at_ms DESC, m.id DESC
                LIMIT ? OFFSET ?
                """,
                (chat_id, min_created_at_ms, safe_limit, safe_offset),
            ).fetchall()
            # Offset counts from the newest message; return oldest-first for rendering.
            rows = list(reversed(rows))
            messages = [self._row_to_message(row) for row in rows]
            attachments_by_id = MediaService(self._db_path, self._storage_root).list_for_chat_messages(
                connection,
                [message.message_id for message in messages],
            )
            reactions_by_id = self._reactions_for_messages(
                connection,
                [message.message_id for message in messages],
                viewer_user_id=requester_user_id,
            )
            polls_by_id = self._polls_for_messages(
                connection,
                [message.message_id for message in messages],
                viewer_user_id=requester_user_id,
            )
            return [
                self._with_message_attachments(
                    connection,
                    message,
                    attachments_by_id=attachments_by_id,
                    reactions_by_id=reactions_by_id,
                    polls_by_id=polls_by_id,
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
        if self._is_platform_moderator(connection, user_id=user_id):
            return True

        kind = str(chat_row["kind"])
        if kind == ChatKind.COMMON.value:
            return True

        if self._row_bool(chat_row, "is_public"):
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
        raw_type = ChatService._row_optional_str_lenient(row, "chat_type") or "group"
        try:
            chat_type = ChatType(raw_type)
        except ValueError:
            chat_type = ChatType.GROUP
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
            avatar_path=ChatService._row_optional_str_lenient(row, "avatar_path"),
            chat_type=chat_type,
            username=ChatService._row_optional_str_lenient(row, "username"),
            is_public=ChatService._row_bool(row, "is_public"),
            slow_mode_seconds=int(ChatService._row_optional_int_lenient(row, "slow_mode_seconds") or 0),
            pinned_message_id=ChatService._row_optional_int_lenient(row, "pinned_message_id"),
            history_visible=ChatService._row_bool_default(row, "history_visible", True),
        )

    @staticmethod
    def _row_to_member(row: sqlite3.Row) -> ChatMember:
        return ChatMember(
            chat_id=ChatService._row_int(row, "chat_id"),
            user_id=ChatService._row_int(row, "user_id"),
            role=ChatMemberRole(str(row["role"])),
            joined_at_ms=ChatService._row_int(row, "joined_at_ms"),
            permissions=ChatService._row_optional_str_lenient(row, "permissions"),
            is_muted=ChatService._row_bool(row, "is_muted"),
            is_archived=ChatService._row_bool(row, "is_archived"),
            is_pinned=ChatService._row_bool(row, "is_pinned"),
            cleared_at_ms=ChatService._row_optional_int_lenient(row, "cleared_at_ms"),
            last_read_message_id=ChatService._row_optional_int_lenient(row, "last_read_message_id"),
        )

    @staticmethod
    def _row_to_invite(row: sqlite3.Row) -> ChatInvite:
        return ChatInvite(
            invite_id=ChatService._row_int(row, "id"),
            chat_id=ChatService._row_int(row, "chat_id"),
            code=str(row["code"]),
            created_by=ChatService._row_optional_int_lenient(row, "created_by"),
            created_at_ms=ChatService._row_int(row, "created_at_ms"),
            expires_at_ms=ChatService._row_optional_int_lenient(row, "expires_at_ms"),
            max_uses=ChatService._row_optional_int_lenient(row, "max_uses"),
            uses=int(ChatService._row_optional_int_lenient(row, "uses") or 0),
            requires_approval=ChatService._row_bool(row, "requires_approval"),
        )

    @staticmethod
    def _row_to_join_request(row: sqlite3.Row) -> ChatJoinRequest:
        return ChatJoinRequest(
            chat_id=ChatService._row_int(row, "chat_id"),
            user_id=ChatService._row_int(row, "user_id"),
            status=str(row["status"]),
            created_at_ms=ChatService._row_int(row, "created_at_ms"),
            decided_by=ChatService._row_optional_int_lenient(row, "decided_by"),
            decided_at_ms=ChatService._row_optional_int_lenient(row, "decided_at_ms"),
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
            reply_to_message_id=ChatService._row_optional_int_lenient(row, "reply_to_message_id"),
            reply_to_login=ChatService._row_optional_str_lenient(row, "reply_login"),
            reply_to_text=ChatService._row_optional_str_lenient(row, "reply_text"),
            forwarded_from_login=ChatService._row_optional_str_lenient(row, "forwarded_from_login"),
            forwarded_from_chat_id=ChatService._row_optional_int_lenient(row, "forwarded_from_chat_id"),
        )

    def _with_message_attachments(
        self,
        connection: sqlite3.Connection,
        message: ChatMessage,
        *,
        attachments_by_id: dict[int, tuple[object, ...]] | None = None,
        reactions_by_id: dict[int, tuple[object, ...]] | None = None,
        polls_by_id: dict[int, object] | None = None,
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
            reply_to_message_id=message.reply_to_message_id,
            reply_to_login=message.reply_to_login,
            reply_to_text=message.reply_to_text,
            forwarded_from_login=message.forwarded_from_login,
            forwarded_from_chat_id=message.forwarded_from_chat_id,
            reactions=(reactions_by_id or {}).get(message.message_id, message.reactions),
            poll=(polls_by_id or {}).get(message.message_id, message.poll),
        )

    def _polls_for_messages(
        self,
        connection: sqlite3.Connection,
        message_ids: Sequence[int],
        *,
        viewer_user_id: int,
    ) -> dict[int, ChatPoll]:
        if not message_ids:
            return {}
        placeholders = ",".join("?" for _ in message_ids)
        rows = connection.execute(
            f"SELECT * FROM chat_polls WHERE message_id IN ({placeholders})",
            tuple(message_ids),
        ).fetchall()
        if not rows:
            return {}

        poll_ids = [int(row["id"]) for row in rows]
        vote_placeholders = ",".join("?" for _ in poll_ids)
        vote_rows = connection.execute(
            f"""
            SELECT poll_id, option_index, COUNT(*) AS total,
                   SUM(CASE WHEN user_id = ? THEN 1 ELSE 0 END) AS mine
            FROM chat_poll_votes
            WHERE poll_id IN ({vote_placeholders})
            GROUP BY poll_id, option_index
            """,
            (viewer_user_id, *poll_ids),
        ).fetchall()

        votes: dict[int, dict[int, tuple[int, bool]]] = {}
        for vote_row in vote_rows:
            votes.setdefault(int(vote_row["poll_id"]), {})[int(vote_row["option_index"])] = (
                int(vote_row["total"]),
                bool(vote_row["mine"]),
            )

        result: dict[int, ChatPoll] = {}
        for row in rows:
            poll_id = int(row["id"])
            try:
                raw_options = json.loads(str(row["options_json"]))
            except (TypeError, ValueError):
                raw_options = []
            if not isinstance(raw_options, list):
                raw_options = []
            options: list[ChatPollOption] = []
            total_votes = 0
            for index, text in enumerate(raw_options):
                count, mine = votes.get(poll_id, {}).get(index, (0, False))
                total_votes += count
                options.append(
                    ChatPollOption(index=index, text=str(text), votes=count, mine=mine)
                )
            poll = ChatPoll(
                poll_id=poll_id,
                question=str(row["question"]),
                options=tuple(options),
                total_votes=total_votes,
                is_multiple=self._row_bool(row, "is_multiple"),
                is_anonymous=self._row_bool(row, "is_anonymous"),
                closed=self._row_optional_int_lenient(row, "closed_at_ms") is not None,
            )
            message_id = self._row_optional_int_lenient(row, "message_id")
            if message_id is not None:
                result[message_id] = poll
        return result

    def _reactions_for_messages(
        self,
        connection: sqlite3.Connection,
        message_ids: Sequence[int],
        *,
        viewer_user_id: int,
    ) -> dict[int, tuple[object, ...]]:
        if not message_ids:
            return {}
        placeholders = ",".join("?" for _ in message_ids)
        rows = connection.execute(
            f"""
            SELECT message_id, emoji, COUNT(*) AS total,
                   SUM(CASE WHEN user_id = ? THEN 1 ELSE 0 END) AS mine
            FROM chat_message_reactions
            WHERE message_id IN ({placeholders})
            GROUP BY message_id, emoji
            """,
            (viewer_user_id, *message_ids),
        ).fetchall()

        grouped: dict[int, list[ChatReaction]] = {}
        for row in rows:
            grouped.setdefault(int(row["message_id"]), []).append(
                ChatReaction(
                    emoji=str(row["emoji"]),
                    count=int(row["total"]),
                    mine=bool(row["mine"]),
                )
            )

        ordered: dict[int, tuple[object, ...]] = {}
        for message_id, items in grouped.items():
            items.sort(key=lambda item: REACTION_EMOJIS.index(item.emoji) if item.emoji in REACTION_EMOJIS else 99)
            ordered[message_id] = tuple(items)
        return ordered

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
    def _resolve_member_ids(
        connection: sqlite3.Connection,
        *,
        creator_user_id: int,
        member_ids: Sequence[int] | None,
    ) -> list[int]:
        """Validate a member list: active accounts only, no guests, no duplicates."""
        if not member_ids:
            return []

        unique_ids: list[int] = []
        for raw in member_ids:
            try:
                user_id = int(raw)
            except (TypeError, ValueError) as exc:
                raise ChatError("invalid_member_id", "Member id must be an integer", 422) from exc
            if user_id <= 0 or user_id == creator_user_id or user_id in unique_ids:
                continue
            unique_ids.append(user_id)

        if not unique_ids:
            return []

        placeholders = ",".join("?" for _ in unique_ids)
        rows = connection.execute(
            f"SELECT id, role, status FROM users WHERE id IN ({placeholders})",
            unique_ids,
        ).fetchall()
        found = {int(row["id"]): row for row in rows}

        for user_id in unique_ids:
            row = found.get(user_id)
            if row is None:
                raise ChatError("member_not_found", "User not found", 404)
            if str(row["status"]) != UserStatus.ACTIVE.value:
                raise ChatError("member_inactive", "User is blocked or banned", 403)
            if str(row["role"]) == UserRole.GUEST.value:
                raise ChatError(
                    "guest_member_forbidden",
                    "Guest accounts cannot be added to chats",
                    403,
                )
        return unique_ids

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
    def _row_optional_int_lenient(row: sqlite3.Row, key: str) -> int | None:
        try:
            value = row[key]
        except Exception:
            return None
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
            SELECT m.*,
                   u.login AS author_login,
                   u.avatar_emoji AS author_avatar_emoji,
                   rm.body_text AS reply_text,
                   ru.login AS reply_login
            FROM chat_messages m
            LEFT JOIN users u ON u.id = m.author_user_id
            LEFT JOIN chat_messages rm ON rm.id = m.reply_to_message_id
            LEFT JOIN users ru ON ru.id = rm.author_user_id
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
    def _row_bool_default(row: sqlite3.Row, key: str, default: bool) -> bool:
        try:
            value = row[key]
        except Exception:
            return default
        if value is None:
            return default
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
            target = connection.execute("SELECT role FROM users WHERE id = ?", (target_user_id,)).fetchone()
            if target is not None and str(target["role"]) == UserRole.GUEST.value:
                raise ChatError(
                    "guest_target",
                    "Guest accounts are one-off: they cannot receive direct messages",
                    403,
                )
            if self._is_blocked_between(connection, user_a=user_id, user_b=target_user_id):
                raise ChatError(
                    "blocked",
                    "Messaging is not available: one of the users is blocked",
                    403,
                )
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
                "INSERT INTO chats (kind, title, description, owner_user_id, is_private, created_at_ms, updated_at_ms, chat_type) VALUES (?, ?, ?, ?, 1, ?, ?, 'dm')",
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

    def search_users(self, query: str, limit: int = 20, viewer_user_id: int | None = None) -> list[dict]:
        """Find people to chat with. Guest accounts are one-off (they expire), so skip them."""
        safe_limit = min(max(limit, 1), 50)
        with self._connect() as connection:
            blocked_filter = ""
            params: list[object] = [UserStatus.ACTIVE.value, UserRole.GUEST.value, f"%{query}%"]
            if viewer_user_id is not None:
                blocked_filter = (
                    " AND id NOT IN (SELECT blocked_user_id FROM user_blocks WHERE blocker_user_id = ?)"
                    " AND id NOT IN (SELECT blocker_user_id FROM user_blocks WHERE blocked_user_id = ?)"
                )
                params.extend([viewer_user_id, viewer_user_id])
            params.append(safe_limit)

            rows = connection.execute(
                f"""
                SELECT id, login, role, status
                FROM users
                WHERE status = ?
                  AND role != ?
                  AND login LIKE ?
                  {blocked_filter}
                ORDER BY login
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
            return [
                {
                    "user_id": int(r["id"]),
                    "login": str(r["login"]),
                    "role": str(r["role"]),
                    "status": str(r["status"]),
                }
                for r in rows
            ]

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
            self._delete_chat_data(connection, chat_id)

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
