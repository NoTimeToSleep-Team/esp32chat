from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from time import time

from app.models import (
    DeviceOwnership,
    DeviceProfile,
    DeviceProfileDraft,
    DeviceProfileView,
    UserRole,
    UserStatus,
)


def _now_ms() -> int:
    return int(time() * 1000)


@dataclass(frozen=True)
class DeviceCatalogError(RuntimeError):
    code: str
    message: str
    status_code: int

    def __str__(self) -> str:
        return self.message


class DeviceCatalogService:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)

    def publish_profile(
        self,
        *,
        actor_user_id: int,
        draft: DeviceProfileDraft,
        is_published: bool = True,
    ) -> DeviceProfile:
        with self._connect() as connection:
            actor = self._require_active_user(connection, actor_user_id)
            if str(actor["role"]) != UserRole.ADMIN.value:
                raise DeviceCatalogError(
                    "admin_only",
                    "Only admin can publish device profiles",
                    403,
                )

            now_ms = _now_ms()
            published_at_ms = now_ms if is_published else None

            try:
                cursor = connection.execute(
                    """
                    INSERT INTO device_catalog(
                        slug,
                        title,
                        short_description,
                        firmware_archive_url,
                        install_guide,
                        pairing_guide,
                        combo_reset_guide,
                        is_published,
                        created_by_user_id,
                        created_at_ms,
                        updated_at_ms,
                        published_at_ms
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        draft.slug.strip().lower(),
                        draft.title.strip(),
                        draft.short_description.strip(),
                        (draft.firmware_archive_url or "").strip() or None,
                        draft.install_guide.strip(),
                        draft.pairing_guide.strip(),
                        draft.combo_reset_guide.strip(),
                        1 if is_published else 0,
                        actor_user_id,
                        now_ms,
                        now_ms,
                        published_at_ms,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise DeviceCatalogError(
                    "device_slug_conflict",
                    "Device profile slug already exists",
                    409,
                ) from exc

            profile_id = self._lastrowid(cursor)
            row = connection.execute(
                "SELECT * FROM device_catalog WHERE id = ?",
                (profile_id,),
            ).fetchone()
            if row is None:
                raise DeviceCatalogError(
                    "device_publish_failed",
                    "Failed to publish device profile",
                    500,
                )
            return self._row_to_profile(row)

    def list_profiles(
        self,
        *,
        requester_user_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DeviceProfileView]:
        safe_limit = min(max(limit, 1), 500)
        safe_offset = max(offset, 0)

        with self._connect() as connection:
            requester = self._require_active_user(connection, requester_user_id)
            is_admin = str(requester["role"]) == UserRole.ADMIN.value

            if is_admin:
                rows = connection.execute(
                    """
                    SELECT
                        d.*,
                        COALESCE(f.has_device, 0) AS has_device
                    FROM device_catalog d
                    LEFT JOIN user_device_flags f
                           ON f.device_id = d.id
                          AND f.user_id = ?
                    ORDER BY COALESCE(d.published_at_ms, d.updated_at_ms) DESC, d.id DESC
                    LIMIT ? OFFSET ?
                    """,
                    (requester_user_id, safe_limit, safe_offset),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT
                        d.*,
                        COALESCE(f.has_device, 0) AS has_device
                    FROM device_catalog d
                    LEFT JOIN user_device_flags f
                           ON f.device_id = d.id
                          AND f.user_id = ?
                    WHERE d.is_published = 1
                    ORDER BY COALESCE(d.published_at_ms, d.updated_at_ms) DESC, d.id DESC
                    LIMIT ? OFFSET ?
                    """,
                    (requester_user_id, safe_limit, safe_offset),
                ).fetchall()

            return [self._row_to_profile_view(row) for row in rows]

    def get_profile(
        self,
        *,
        requester_user_id: int,
        device_id: int,
    ) -> DeviceProfileView:
        with self._connect() as connection:
            requester = self._require_active_user(connection, requester_user_id)
            is_admin = str(requester["role"]) == UserRole.ADMIN.value

            if is_admin:
                row = connection.execute(
                    """
                    SELECT
                        d.*,
                        COALESCE(f.has_device, 0) AS has_device
                    FROM device_catalog d
                    LEFT JOIN user_device_flags f
                           ON f.device_id = d.id
                          AND f.user_id = ?
                    WHERE d.id = ?
                    """,
                    (requester_user_id, device_id),
                ).fetchone()
            else:
                row = connection.execute(
                    """
                    SELECT
                        d.*,
                        COALESCE(f.has_device, 0) AS has_device
                    FROM device_catalog d
                    LEFT JOIN user_device_flags f
                           ON f.device_id = d.id
                          AND f.user_id = ?
                    WHERE d.id = ? AND d.is_published = 1
                    """,
                    (requester_user_id, device_id),
                ).fetchone()

            if row is None:
                raise DeviceCatalogError(
                    "device_not_found",
                    "Device profile was not found",
                    404,
                )
            return self._row_to_profile_view(row)

    def set_ownership(
        self,
        *,
        requester_user_id: int,
        device_id: int,
        has_device: bool,
    ) -> DeviceOwnership:
        with self._connect() as connection:
            requester = self._require_active_user(connection, requester_user_id)
            role = str(requester["role"])

            if role == UserRole.GUEST.value:
                raise DeviceCatalogError(
                    "guest_not_allowed",
                    "Guest account cannot set device ownership",
                    403,
                )

            if role == UserRole.ADMIN.value:
                exists = connection.execute(
                    "SELECT id FROM device_catalog WHERE id = ?",
                    (device_id,),
                ).fetchone()
            else:
                exists = connection.execute(
                    "SELECT id FROM device_catalog WHERE id = ? AND is_published = 1",
                    (device_id,),
                ).fetchone()

            if exists is None:
                raise DeviceCatalogError(
                    "device_not_found",
                    "Device profile was not found",
                    404,
                )

            now_ms = _now_ms()
            connection.execute(
                """
                INSERT INTO user_device_flags(user_id, device_id, has_device, updated_at_ms)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, device_id)
                DO UPDATE SET
                    has_device = excluded.has_device,
                    updated_at_ms = excluded.updated_at_ms
                """,
                (
                    requester_user_id,
                    device_id,
                    1 if has_device else 0,
                    now_ms,
                ),
            )

            row = connection.execute(
                """
                SELECT user_id, device_id, has_device, updated_at_ms
                FROM user_device_flags
                WHERE user_id = ? AND device_id = ?
                """,
                (requester_user_id, device_id),
            ).fetchone()
            if row is None:
                raise DeviceCatalogError(
                    "ownership_update_failed",
                    "Failed to update device ownership",
                    500,
                )

            return DeviceOwnership(
                user_id=int(row["user_id"]),
                device_id=int(row["device_id"]),
                has_device=bool(int(row["has_device"])),
                updated_at_ms=int(row["updated_at_ms"]),
            )

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
            raise DeviceCatalogError("user_not_found", "User was not found", 404)
        if str(row["status"]) != UserStatus.ACTIVE.value:
            raise DeviceCatalogError("inactive_user", "User account is not active", 403)
        return row

    @staticmethod
    def _row_to_profile(row: sqlite3.Row) -> DeviceProfile:
        return DeviceProfile(
            device_id=int(row["id"]),
            slug=str(row["slug"]),
            title=str(row["title"]),
            short_description=str(row["short_description"]),
            firmware_archive_url=str(row["firmware_archive_url"])
            if row["firmware_archive_url"] is not None
            else None,
            install_guide=str(row["install_guide"]),
            pairing_guide=str(row["pairing_guide"]),
            combo_reset_guide=str(row["combo_reset_guide"]),
            is_published=bool(int(row["is_published"])),
            created_by_user_id=int(row["created_by_user_id"]),
            created_at_ms=int(row["created_at_ms"]),
            updated_at_ms=int(row["updated_at_ms"]),
            published_at_ms=int(row["published_at_ms"])
            if row["published_at_ms"] is not None
            else None,
        )

    @staticmethod
    def _row_to_profile_view(row: sqlite3.Row) -> DeviceProfileView:
        return DeviceProfileView(
            profile=DeviceCatalogService._row_to_profile(row),
            has_device=bool(int(row["has_device"])),
        )

    @staticmethod
    def _lastrowid(cursor: sqlite3.Cursor) -> int:
        value = cursor.lastrowid
        if value is None:
            raise DeviceCatalogError("invalid_data", "lastrowid is missing", 500)
        return int(value)
