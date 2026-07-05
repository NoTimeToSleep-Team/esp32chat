from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from time import time

from app.models import AdminUserRecord, DeviceBlacklistEntry, UserRole, UserStatus


def _now_ms() -> int:
    return int(time() * 1000)


@dataclass(frozen=True)
class AdminUsersError(RuntimeError):
    code: str
    message: str
    status_code: int

    def __str__(self) -> str:
        return self.message


class AdminUsersService:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)

    def list_users(
        self,
        *,
        actor_user_id: int,
        status: UserStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AdminUserRecord]:
        safe_limit = min(max(limit, 1), 500)
        safe_offset = max(offset, 0)

        with self._connect() as connection:
            self._require_active_admin(connection, actor_user_id)

            if status is None:
                rows = connection.execute(
                    """
                    SELECT
                        u.id,
                        u.login,
                        u.role,
                        u.status,
                        u.phone,
                        u.registration_device_id,
                        u.created_at_ms,
                        u.updated_at_ms,
                        r.block_reason,
                        r.blocked_until_ms,
                        r.updated_by_user_id AS restriction_updated_by_user_id,
                        r.updated_at_ms AS restriction_updated_at_ms,
                        CASE WHEN b.device_id IS NOT NULL THEN 1 ELSE 0 END AS device_blacklisted
                    FROM users u
                    LEFT JOIN user_restrictions r ON r.user_id = u.id
                    LEFT JOIN device_blacklist b ON b.device_id = u.registration_device_id
                    ORDER BY u.created_at_ms DESC, u.id DESC
                    LIMIT ? OFFSET ?
                    """,
                    (safe_limit, safe_offset),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT
                        u.id,
                        u.login,
                        u.role,
                        u.status,
                        u.phone,
                        u.registration_device_id,
                        u.created_at_ms,
                        u.updated_at_ms,
                        r.block_reason,
                        r.blocked_until_ms,
                        r.updated_by_user_id AS restriction_updated_by_user_id,
                        r.updated_at_ms AS restriction_updated_at_ms,
                        CASE WHEN b.device_id IS NOT NULL THEN 1 ELSE 0 END AS device_blacklisted
                    FROM users u
                    LEFT JOIN user_restrictions r ON r.user_id = u.id
                    LEFT JOIN device_blacklist b ON b.device_id = u.registration_device_id
                    WHERE u.status = ?
                    ORDER BY u.created_at_ms DESC, u.id DESC
                    LIMIT ? OFFSET ?
                    """,
                    (status.value, safe_limit, safe_offset),
                ).fetchall()

            return [self._row_to_admin_user(row) for row in rows]

    def get_user(
        self,
        *,
        actor_user_id: int,
        target_user_id: int,
    ) -> AdminUserRecord:
        with self._connect() as connection:
            self._require_active_admin(connection, actor_user_id)
            row = self._select_admin_user(connection, user_id=target_user_id)
            if row is None:
                raise AdminUsersError("user_not_found", "User was not found", 404)
            return self._row_to_admin_user(row)

    def ban_user(
        self,
        *,
        actor_user_id: int,
        target_user_id: int,
        reason: str | None = None,
    ) -> AdminUserRecord:
        with self._connect() as connection:
            self._require_active_admin(connection, actor_user_id)
            self._ensure_target_allowed(connection, actor_user_id=actor_user_id, target_user_id=target_user_id)

            now_ms = _now_ms()
            normalized_reason = (reason or "").strip() or "banned by admin"

            connection.execute(
                "UPDATE users SET status = ?, updated_at_ms = ? WHERE id = ?",
                (UserStatus.BANNED.value, now_ms, target_user_id),
            )
            self._upsert_restriction(
                connection,
                user_id=target_user_id,
                block_reason=normalized_reason,
                blocked_until_ms=None,
                updated_by_user_id=actor_user_id,
                updated_at_ms=now_ms,
            )

            row = self._select_admin_user(connection, user_id=target_user_id)
            if row is None:
                raise AdminUsersError("user_not_found", "User was not found", 404)
            return self._row_to_admin_user(row)

    def unban_user(
        self,
        *,
        actor_user_id: int,
        target_user_id: int,
    ) -> AdminUserRecord:
        with self._connect() as connection:
            self._require_active_admin(connection, actor_user_id)
            self._ensure_target_exists(connection, target_user_id)

            now_ms = _now_ms()
            connection.execute(
                "UPDATE users SET status = ?, updated_at_ms = ? WHERE id = ?",
                (UserStatus.ACTIVE.value, now_ms, target_user_id),
            )
            self._upsert_restriction(
                connection,
                user_id=target_user_id,
                block_reason=None,
                blocked_until_ms=None,
                updated_by_user_id=actor_user_id,
                updated_at_ms=now_ms,
            )

            row = self._select_admin_user(connection, user_id=target_user_id)
            if row is None:
                raise AdminUsersError("user_not_found", "User was not found", 404)
            return self._row_to_admin_user(row)

    def temporary_block_user(
        self,
        *,
        actor_user_id: int,
        target_user_id: int,
        duration_minutes: int,
        reason: str | None = None,
    ) -> AdminUserRecord:
        if duration_minutes < 1 or duration_minutes > 7 * 24 * 60:
            raise AdminUsersError(
                "invalid_block_duration",
                "duration_minutes must be in range 1..10080",
                422,
            )

        with self._connect() as connection:
            self._require_active_admin(connection, actor_user_id)
            self._ensure_target_allowed(connection, actor_user_id=actor_user_id, target_user_id=target_user_id)

            now_ms = _now_ms()
            blocked_until_ms = now_ms + duration_minutes * 60_000
            normalized_reason = (
                (reason or "").strip()
                or f"temporarily blocked for {duration_minutes} minutes"
            )

            connection.execute(
                "UPDATE users SET status = ?, updated_at_ms = ? WHERE id = ?",
                (UserStatus.BLOCKED.value, now_ms, target_user_id),
            )
            self._upsert_restriction(
                connection,
                user_id=target_user_id,
                block_reason=normalized_reason,
                blocked_until_ms=blocked_until_ms,
                updated_by_user_id=actor_user_id,
                updated_at_ms=now_ms,
            )

            row = self._select_admin_user(connection, user_id=target_user_id)
            if row is None:
                raise AdminUsersError("user_not_found", "User was not found", 404)
            return self._row_to_admin_user(row)

    def blacklist_device(
        self,
        *,
        actor_user_id: int,
        target_user_id: int,
        reason: str | None = None,
        device_id: str | None = None,
    ) -> tuple[AdminUserRecord, DeviceBlacklistEntry]:
        with self._connect() as connection:
            self._require_active_admin(connection, actor_user_id)
            target = self._ensure_target_exists(connection, target_user_id)

            selected_device_id = (device_id or "").strip() or self._row_optional_str(
                target,
                "registration_device_id",
            )
            if not selected_device_id:
                raise AdminUsersError(
                    "device_id_missing",
                    "No device id was provided and user has no registered device id",
                    422,
                )

            now_ms = _now_ms()
            normalized_reason = (reason or "").strip() or None

            connection.execute(
                """
                INSERT INTO device_blacklist(device_id, reason, blocked_by_user_id, created_at_ms, updated_at_ms)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(device_id)
                DO UPDATE SET
                    reason = excluded.reason,
                    blocked_by_user_id = excluded.blocked_by_user_id,
                    updated_at_ms = excluded.updated_at_ms
                """,
                (
                    selected_device_id,
                    normalized_reason,
                    actor_user_id,
                    now_ms,
                    now_ms,
                ),
            )

            entry_row = connection.execute(
                "SELECT * FROM device_blacklist WHERE device_id = ?",
                (selected_device_id,),
            ).fetchone()
            user_row = self._select_admin_user(connection, user_id=target_user_id)
            if entry_row is None or user_row is None:
                raise AdminUsersError(
                    "blacklist_update_failed",
                    "Failed to update device blacklist",
                    500,
                )
            return self._row_to_admin_user(user_row), self._row_to_blacklist_entry(entry_row)

    def unblacklist_device(
        self,
        *,
        actor_user_id: int,
        target_user_id: int,
        device_id: str | None = None,
    ) -> AdminUserRecord:
        with self._connect() as connection:
            self._require_active_admin(connection, actor_user_id)
            target = self._ensure_target_exists(connection, target_user_id)

            selected_device_id = (device_id or "").strip() or self._row_optional_str(
                target,
                "registration_device_id",
            )
            if not selected_device_id:
                raise AdminUsersError(
                    "device_id_missing",
                    "No device id was provided and user has no registered device id",
                    422,
                )

            deleted = connection.execute(
                "DELETE FROM device_blacklist WHERE device_id = ?",
                (selected_device_id,),
            ).rowcount
            if deleted <= 0:
                raise AdminUsersError(
                    "device_not_blacklisted",
                    "Device id is not blacklisted",
                    404,
                )

            user_row = self._select_admin_user(connection, user_id=target_user_id)
            if user_row is None:
                raise AdminUsersError("user_not_found", "User was not found", 404)
            return self._row_to_admin_user(user_row)

    def delete_user(
        self,
        *,
        actor_user_id: int,
        target_user_id: int,
    ) -> tuple[int, str]:
        with self._connect() as connection:
            self._require_active_admin(connection, actor_user_id)
            if actor_user_id == target_user_id:
                raise AdminUsersError(
                    "self_delete_forbidden",
                    "Admin cannot delete own account",
                    409,
                )

            target = self._ensure_target_exists(connection, target_user_id)
            target_role = str(target["role"])
            target_login = str(target["login"])

            if target_role == UserRole.ADMIN.value:
                row = connection.execute(
                    """
                    SELECT COUNT(*) AS total
                    FROM users
                    WHERE role = ?
                    """,
                    (UserRole.ADMIN.value,),
                ).fetchone()
                total_admins = int(row["total"]) if row is not None else 0
                if total_admins <= 1:
                    raise AdminUsersError(
                        "last_admin_forbidden",
                        "Cannot delete last admin account",
                        409,
                    )

            deleted = connection.execute(
                "DELETE FROM users WHERE id = ?",
                (target_user_id,),
            ).rowcount
            if deleted <= 0:
                raise AdminUsersError("user_not_found", "User was not found", 404)

            return target_user_id, target_login

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _require_active_admin(connection: sqlite3.Connection, user_id: int) -> sqlite3.Row:
        row = connection.execute(
            "SELECT id, role, status FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            raise AdminUsersError("admin_not_found", "Admin user was not found", 404)
        if str(row["status"]) != UserStatus.ACTIVE.value or str(row["role"]) != UserRole.ADMIN.value:
            raise AdminUsersError("admin_only", "Admin role is required", 403)
        return row

    @staticmethod
    def _ensure_target_exists(connection: sqlite3.Connection, user_id: int) -> sqlite3.Row:
        row = connection.execute(
            "SELECT id, login, role, status, registration_device_id FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            raise AdminUsersError("user_not_found", "User was not found", 404)
        return row

    @staticmethod
    def _ensure_target_allowed(
        connection: sqlite3.Connection,
        *,
        actor_user_id: int,
        target_user_id: int,
    ) -> sqlite3.Row:
        if actor_user_id == target_user_id:
            raise AdminUsersError(
                "self_action_forbidden",
                "Admin cannot apply this action to own account",
                409,
            )
        return AdminUsersService._ensure_target_exists(connection, target_user_id)

    @staticmethod
    def _upsert_restriction(
        connection: sqlite3.Connection,
        *,
        user_id: int,
        block_reason: str | None,
        blocked_until_ms: int | None,
        updated_by_user_id: int,
        updated_at_ms: int,
    ) -> None:
        connection.execute(
            """
            INSERT INTO user_restrictions(
                user_id,
                block_reason,
                blocked_until_ms,
                updated_by_user_id,
                updated_at_ms
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id)
            DO UPDATE SET
                block_reason = excluded.block_reason,
                blocked_until_ms = excluded.blocked_until_ms,
                updated_by_user_id = excluded.updated_by_user_id,
                updated_at_ms = excluded.updated_at_ms
            """,
            (
                user_id,
                block_reason,
                blocked_until_ms,
                updated_by_user_id,
                updated_at_ms,
            ),
        )

    @staticmethod
    def _select_admin_user(connection: sqlite3.Connection, *, user_id: int) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT
                u.id,
                u.login,
                u.role,
                u.status,
                u.phone,
                u.registration_device_id,
                u.created_at_ms,
                u.updated_at_ms,
                r.block_reason,
                r.blocked_until_ms,
                r.updated_by_user_id AS restriction_updated_by_user_id,
                r.updated_at_ms AS restriction_updated_at_ms,
                CASE WHEN b.device_id IS NOT NULL THEN 1 ELSE 0 END AS device_blacklisted
            FROM users u
            LEFT JOIN user_restrictions r ON r.user_id = u.id
            LEFT JOIN device_blacklist b ON b.device_id = u.registration_device_id
            WHERE u.id = ?
            """,
            (user_id,),
        ).fetchone()

    @staticmethod
    def _row_to_admin_user(row: sqlite3.Row) -> AdminUserRecord:
        return AdminUserRecord(
            user_id=int(row["id"]),
            login=str(row["login"]),
            role=UserRole(str(row["role"])),
            status=UserStatus(str(row["status"])),
            phone=AdminUsersService._row_optional_str(row, "phone"),
            registration_device_id=AdminUsersService._row_optional_str(row, "registration_device_id"),
            created_at_ms=int(row["created_at_ms"]),
            updated_at_ms=int(row["updated_at_ms"]),
            block_reason=AdminUsersService._row_optional_str(row, "block_reason"),
            blocked_until_ms=AdminUsersService._row_optional_int(row, "blocked_until_ms"),
            restriction_updated_by_user_id=AdminUsersService._row_optional_int(
                row,
                "restriction_updated_by_user_id",
            ),
            restriction_updated_at_ms=AdminUsersService._row_optional_int(
                row,
                "restriction_updated_at_ms",
            ),
            device_blacklisted=bool(int(row["device_blacklisted"])),
        )

    @staticmethod
    def _row_to_blacklist_entry(row: sqlite3.Row) -> DeviceBlacklistEntry:
        return DeviceBlacklistEntry(
            device_id=str(row["device_id"]),
            reason=AdminUsersService._row_optional_str(row, "reason"),
            blocked_by_user_id=int(row["blocked_by_user_id"]),
            created_at_ms=int(row["created_at_ms"]),
            updated_at_ms=int(row["updated_at_ms"]),
        )

    @staticmethod
    def _row_optional_str(row: sqlite3.Row, key: str) -> str | None:
        value = row[key]
        return str(value) if value is not None else None

    @staticmethod
    def _row_optional_int(row: sqlite3.Row, key: str) -> int | None:
        value = row[key]
        return int(value) if value is not None else None
