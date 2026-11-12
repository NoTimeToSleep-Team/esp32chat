from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from time import time

from app.models import UserRole, UserStatus
from app.db.connection import connect_sqlite


def _now_ms() -> int:
    return int(time() * 1000)


def _hash_combo(actions: list[str], *, iterations: int = 210_000) -> str:
    salt = secrets.token_hex(16)
    normalized = _combo_material(actions)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        normalized.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    )
    return f"pbkdf2_sha256${iterations}${salt}${digest.hex()}"


def _verify_combo(actions: list[str], combo_hash: str) -> bool:
    parts = combo_hash.split("$")
    if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
        return False
    try:
        iterations = int(parts[1])
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac(
        "sha256",
        _combo_material(actions).encode("utf-8"),
        parts[2].encode("utf-8"),
        iterations,
    ).hex()
    return hmac.compare_digest(candidate, parts[3])


def _combo_material(actions: list[str]) -> str:
    return json.dumps(actions, ensure_ascii=True, separators=(",", ":"))


@dataclass(frozen=True)
class DeviceComboRecord:
    user_id: int
    device_id: str
    combo_actions_count: int
    failure_count: int
    locked_until_ms: int | None
    created_at_ms: int
    updated_at_ms: int
    verified_at_ms: int | None
    reset_at_ms: int | None


@dataclass(frozen=True)
class DeviceComboVerifyResult:
    verified: bool
    record: DeviceComboRecord | None


@dataclass(frozen=True)
class DeviceComboError(RuntimeError):
    code: str
    message: str
    status_code: int

    def __str__(self) -> str:
        return self.message


class DeviceComboService:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)

    def set_combo(
        self,
        *,
        user_id: int,
        device_id: str,
        actions: list[str],
    ) -> DeviceComboRecord:
        normalized_device_id = self._normalize_device_id(device_id)
        normalized_actions = self._normalize_actions(actions)
        combo_hash = _hash_combo(normalized_actions)
        now_ms = _now_ms()

        with self._connect() as connection:
            self._require_registered_active_user(connection, user_id)
            connection.execute(
                """
                INSERT INTO device_combo_hashes(
                    user_id,
                    device_id,
                    combo_hash,
                    combo_hash_algorithm,
                    combo_actions_count,
                    failure_count,
                    locked_until_ms,
                    created_at_ms,
                    updated_at_ms,
                    verified_at_ms,
                    reset_at_ms
                )
                VALUES (?, ?, ?, 'pbkdf2_sha256', ?, 0, NULL, ?, ?, NULL, NULL)
                ON CONFLICT(user_id, device_id)
                DO UPDATE SET
                    combo_hash = excluded.combo_hash,
                    combo_hash_algorithm = excluded.combo_hash_algorithm,
                    combo_actions_count = excluded.combo_actions_count,
                    failure_count = 0,
                    locked_until_ms = NULL,
                    updated_at_ms = excluded.updated_at_ms,
                    reset_at_ms = NULL
                """,
                (
                    user_id,
                    normalized_device_id,
                    combo_hash,
                    len(normalized_actions),
                    now_ms,
                    now_ms,
                ),
            )
            return self._read_record(connection, user_id=user_id, device_id=normalized_device_id)

    def reset_combo(self, *, user_id: int, device_id: str) -> DeviceComboRecord | None:
        normalized_device_id = self._normalize_device_id(device_id)
        now_ms = _now_ms()
        with self._connect() as connection:
            self._require_registered_active_user(connection, user_id)
            row = connection.execute(
                """
                SELECT * FROM device_combo_hashes
                WHERE user_id = ? AND device_id = ?
                """,
                (user_id, normalized_device_id),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                """
                UPDATE device_combo_hashes
                SET combo_hash = '',
                    combo_actions_count = 3,
                    failure_count = 0,
                    locked_until_ms = NULL,
                    updated_at_ms = ?,
                    reset_at_ms = ?
                WHERE user_id = ? AND device_id = ?
                """,
                (now_ms, now_ms, user_id, normalized_device_id),
            )
            return self._read_record(connection, user_id=user_id, device_id=normalized_device_id)

    def verify_combo(
        self,
        *,
        user_id: int,
        device_id: str,
        actions: list[str],
    ) -> DeviceComboVerifyResult:
        normalized_device_id = self._normalize_device_id(device_id)
        normalized_actions = self._normalize_actions(actions)
        now_ms = _now_ms()

        with self._connect() as connection:
            self._require_registered_active_user(connection, user_id)
            row = connection.execute(
                """
                SELECT * FROM device_combo_hashes
                WHERE user_id = ? AND device_id = ?
                """,
                (user_id, normalized_device_id),
            ).fetchone()
            if row is None or not str(row["combo_hash"]):
                raise DeviceComboError(
                    "combo_not_set",
                    "Device combo is not set for this user/device",
                    404,
                )

            locked_until_ms = row["locked_until_ms"]
            if locked_until_ms is not None and int(locked_until_ms) > now_ms:
                raise DeviceComboError(
                    "combo_locked",
                    "Too many failed combo attempts, try later",
                    429,
                )

            verified = _verify_combo(normalized_actions, str(row["combo_hash"]))
            if verified:
                connection.execute(
                    """
                    UPDATE device_combo_hashes
                    SET failure_count = 0,
                        locked_until_ms = NULL,
                        verified_at_ms = ?,
                        updated_at_ms = ?
                    WHERE user_id = ? AND device_id = ?
                    """,
                    (now_ms, now_ms, user_id, normalized_device_id),
                )
            else:
                next_failures = int(row["failure_count"]) + 1
                next_locked_until = now_ms + 300_000 if next_failures >= 5 else None
                connection.execute(
                    """
                    UPDATE device_combo_hashes
                    SET failure_count = ?,
                        locked_until_ms = ?,
                        updated_at_ms = ?
                    WHERE user_id = ? AND device_id = ?
                    """,
                    (next_failures, next_locked_until, now_ms, user_id, normalized_device_id),
                )

            record = self._read_record(connection, user_id=user_id, device_id=normalized_device_id)
            return DeviceComboVerifyResult(verified=verified, record=record)

    def _connect(self) -> sqlite3.Connection:
        return connect_sqlite(self._db_path)

    @staticmethod
    def _normalize_device_id(device_id: str) -> str:
        normalized = device_id.strip()
        if not normalized or len(normalized) > 256:
            raise DeviceComboError("invalid_device_id", "Invalid device_id", 422)
        return normalized

    @staticmethod
    def _normalize_actions(actions: list[str]) -> list[str]:
        normalized = [str(action).strip().lower() for action in actions]
        if len(normalized) < 1:
            raise DeviceComboError("combo_empty", "Device combo must not be empty", 422)
        if len(normalized) > 32:
            raise DeviceComboError("combo_too_long", "Device combo is too long", 422)
        for action in normalized:
            if not action or len(action) > 64:
                raise DeviceComboError("invalid_combo_action", "Invalid combo action", 422)
        return normalized

    @staticmethod
    def _require_registered_active_user(connection: sqlite3.Connection, user_id: int) -> None:
        row = connection.execute(
            "SELECT id, role, status FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            raise DeviceComboError("user_not_found", "User was not found", 404)
        if str(row["status"]) != UserStatus.ACTIVE.value:
            raise DeviceComboError("inactive_user", "User account is not active", 403)
        if str(row["role"]) == UserRole.GUEST.value:
            raise DeviceComboError(
                "guest_hardware_login_forbidden",
                "Guest accounts cannot use hardware device combos",
                403,
            )

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> DeviceComboRecord:
        return DeviceComboRecord(
            user_id=int(row["user_id"]),
            device_id=str(row["device_id"]),
            combo_actions_count=int(row["combo_actions_count"]),
            failure_count=int(row["failure_count"]),
            locked_until_ms=int(row["locked_until_ms"])
            if row["locked_until_ms"] is not None
            else None,
            created_at_ms=int(row["created_at_ms"]),
            updated_at_ms=int(row["updated_at_ms"]),
            verified_at_ms=int(row["verified_at_ms"])
            if row["verified_at_ms"] is not None
            else None,
            reset_at_ms=int(row["reset_at_ms"])
            if row["reset_at_ms"] is not None
            else None,
        )

    def _read_record(
        self,
        connection: sqlite3.Connection,
        *,
        user_id: int,
        device_id: str,
    ) -> DeviceComboRecord:
        row = connection.execute(
            """
            SELECT * FROM device_combo_hashes
            WHERE user_id = ? AND device_id = ?
            """,
            (user_id, device_id),
        ).fetchone()
        if row is None:
            raise DeviceComboError("combo_not_found", "Device combo was not found", 404)
        return self._row_to_record(row)
