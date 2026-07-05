from __future__ import annotations

import secrets
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from time import time

from app.models import (
    AccountLimits,
    AccountProfile,
    AccountProfileUpdate,
    AvatarImage,
    ChatKind,
    UserConstraints,
    UserRole,
    UserStatus,
)


def _now_ms() -> int:
    return int(time() * 1000)


_AVATAR_EXT_BY_MIME: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}

_AVATAR_MIME_BY_EXT: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


@dataclass(frozen=True)
class AccountError(RuntimeError):
    code: str
    message: str
    status_code: int

    def __str__(self) -> str:
        return self.message


class AccountService:
    def __init__(self, db_path: str | Path, *, avatars_root: str | Path) -> None:
        self._db_path = Path(db_path)
        self._avatars_root = Path(avatars_root)

    def get_profile(self, *, user_id: int) -> AccountProfile:
        with self._connect() as connection:
            row = self._require_active_user(connection, user_id)
            return self._row_to_profile(row)

    def update_profile(
        self,
        *,
        user_id: int,
        draft: AccountProfileUpdate,
    ) -> AccountProfile:
        with self._connect() as connection:
            row = self._require_active_user(connection, user_id)
            self._require_profile_owner_role(row)

            display_name = (
                (draft.display_name or "").strip() or None
                if draft.display_name is not None
                else self._row_optional_str(row, "display_name")
            )
            profile_bio = (
                (draft.profile_bio or "").strip() or None
                if draft.profile_bio is not None
                else self._row_optional_str(row, "profile_bio")
            )

            now_ms = _now_ms()
            connection.execute(
                """
                UPDATE users
                SET display_name = ?,
                    profile_bio = ?,
                    updated_at_ms = ?
                WHERE id = ?
                """,
                (display_name, profile_bio, now_ms, user_id),
            )

            updated = connection.execute(
                "SELECT * FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            if updated is None:
                raise AccountError("user_not_found", "User was not found", 404)
            return self._row_to_profile(updated)

    def set_avatar(self, *, user_id: int, avatar: AvatarImage) -> AccountProfile:
        normalized_mime = avatar.mime_type.strip().lower()
        extension = _AVATAR_EXT_BY_MIME.get(normalized_mime)
        if extension is None:
            raise AccountError(
                "invalid_avatar_mime",
                "Avatar image must be png, jpeg or webp",
                422,
            )
        if len(avatar.content) > 2_000_000:
            raise AccountError("avatar_too_large", "Avatar image must be <= 2MB", 422)

        with self._connect() as connection:
            row = self._require_active_user(connection, user_id)
            self._require_profile_owner_role(row)

            now_ms = _now_ms()
            avatar_name = f"u{user_id}_{now_ms}_{secrets.token_hex(6)}{extension}"
            self._avatars_root.mkdir(parents=True, exist_ok=True)
            new_path = self._avatars_root / avatar_name

            try:
                new_path.write_bytes(avatar.content)
            except OSError as exc:
                raise AccountError("avatar_write_failed", "Failed to save avatar image", 500) from exc

            old_avatar = self._row_optional_str(row, "avatar_path")

            connection.execute(
                """
                UPDATE users
                SET avatar_path = ?,
                    avatar_updated_at_ms = ?,
                    updated_at_ms = ?
                WHERE id = ?
                """,
                (avatar_name, now_ms, now_ms, user_id),
            )

            updated = connection.execute(
                "SELECT * FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            if updated is None:
                raise AccountError("user_not_found", "User was not found", 404)

            self._delete_old_avatar_file(old_avatar)
            return self._row_to_profile(updated)

    def get_avatar_file(self, *, user_id: int) -> tuple[Path, str]:
        with self._connect() as connection:
            row = self._require_active_user(connection, user_id)
            avatar_path = self._row_optional_str(row, "avatar_path")
            if not avatar_path:
                raise AccountError("avatar_not_set", "Avatar is not set", 404)

            file_path = (self._avatars_root / avatar_path).resolve()
            avatars_root = self._avatars_root.resolve()
            try:
                file_path.relative_to(avatars_root)
            except ValueError as exc:
                raise AccountError("avatar_invalid_path", "Avatar path is invalid", 500) from exc

            if not file_path.exists() or not file_path.is_file():
                raise AccountError("avatar_not_found", "Avatar file was not found", 404)

            mime = _AVATAR_MIME_BY_EXT.get(file_path.suffix.lower(), "application/octet-stream")
            return file_path, mime

    def get_limits(self, *, user_id: int) -> AccountLimits:
        with self._connect() as connection:
            user = self._require_active_user(connection, user_id)
            role = UserRole(str(user["role"]))

            row = connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM chats
                WHERE kind = ? AND owner_user_id = ?
                """,
                (ChatKind.CUSTOM.value, user_id),
            ).fetchone()
            current = int(row["total"]) if row is not None else 0

            if role == UserRole.ADMIN:
                return AccountLimits(
                    role=role,
                    max_custom_chats=None,
                    current_custom_chats=current,
                    remaining_custom_chats=None,
                    can_create_custom_chats=True,
                )

            if role == UserRole.GUEST:
                return AccountLimits(
                    role=role,
                    max_custom_chats=0,
                    current_custom_chats=current,
                    remaining_custom_chats=0,
                    can_create_custom_chats=False,
                )

            rules = UserConstraints()
            remaining = max(rules.max_user_custom_chats - current, 0)

            return AccountLimits(
                role=role,
                max_custom_chats=rules.max_user_custom_chats,
                current_custom_chats=current,
                remaining_custom_chats=remaining,
                can_create_custom_chats=remaining > 0,
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _require_active_user(connection: sqlite3.Connection, user_id: int) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            raise AccountError("user_not_found", "User was not found", 404)
        if str(row["status"]) != UserStatus.ACTIVE.value:
            raise AccountError("inactive_user", "User account is not active", 403)
        return row

    @staticmethod
    def _require_profile_owner_role(user_row: sqlite3.Row) -> None:
        role = str(user_row["role"])
        if role == UserRole.GUEST.value:
            raise AccountError("guest_not_allowed", "Guest account cannot change profile", 403)

    def _delete_old_avatar_file(self, old_avatar: str | None) -> None:
        if not old_avatar:
            return

        avatars_root = self._avatars_root.resolve()
        old_path = (self._avatars_root / old_avatar).resolve()
        try:
            old_path.relative_to(avatars_root)
        except ValueError:
            return

        if old_path.exists() and old_path.is_file():
            try:
                old_path.unlink()
            except OSError:
                return

    @staticmethod
    def _row_to_profile(row: sqlite3.Row) -> AccountProfile:
        return AccountProfile(
            user_id=int(row["id"]),
            login=str(row["login"]),
            role=UserRole(str(row["role"])),
            status=UserStatus(str(row["status"])),
            phone=AccountService._row_optional_str(row, "phone"),
            display_name=AccountService._row_optional_str(row, "display_name"),
            profile_bio=AccountService._row_optional_str(row, "profile_bio"),
            avatar_path=AccountService._row_optional_str(row, "avatar_path"),
            avatar_updated_at_ms=AccountService._row_optional_int(row, "avatar_updated_at_ms"),
        )

    @staticmethod
    def _row_optional_str(row: sqlite3.Row, key: str) -> str | None:
        try:
            value = row[key]
        except Exception:
            return None
        return str(value) if value is not None else None

    @staticmethod
    def _row_optional_int(row: sqlite3.Row, key: str) -> int | None:
        try:
            value = row[key]
        except Exception:
            return None
        return int(value) if value is not None else None
