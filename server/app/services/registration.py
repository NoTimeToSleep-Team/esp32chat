from __future__ import annotations

import secrets
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from time import time

from app.models import AccessMode, ClientKind, User, UserRole, UserStatus
from app.services.auth import AuthResult, SessionInfo, hash_password


def _now_ms() -> int:
    return int(time() * 1000)


@dataclass(frozen=True)
class RegistrationError(RuntimeError):
    code: str
    message: str
    status_code: int

    def __str__(self) -> str:
        return self.message


class RegistrationService:
    def __init__(self, db_path: str | Path, *, session_ttl_ms: int = 86_400_000) -> None:
        self._db_path = Path(db_path)
        self._session_ttl_ms = session_ttl_ms

    def register_user(
        self,
        *,
        login: str,
        password: str,
        phone: str,
        device_id: str,
        client_kind: ClientKind,
    ) -> AuthResult:
        normalized_login = login.strip()
        normalized_phone = self._normalize_phone(phone)
        normalized_device_id = self._normalize_device_id(device_id)

        if not normalized_login:
            raise RegistrationError("invalid_login", "Login must not be empty", 422)
        if len(password) < 8:
            raise RegistrationError("weak_password", "Password must be at least 8 characters", 422)
        if not normalized_phone:
            raise RegistrationError("invalid_phone", "Phone must not be empty", 422)
        if not normalized_device_id:
            raise RegistrationError("invalid_device", "Device id must not be empty", 422)

        with self._connect() as connection:
            access_mode = self._read_access_mode(connection)
            if access_mode != AccessMode.OPEN:
                raise RegistrationError(
                    "registration_disabled_closed_mode",
                    "Registration is available only in open mode",
                    409,
                )

            if self._is_device_blacklisted(connection, normalized_device_id):
                raise RegistrationError(
                    "device_blacklisted",
                    "Device is blacklisted",
                    403,
                )

            if connection.execute(
                "SELECT id FROM users WHERE login = ?",
                (normalized_login,),
            ).fetchone() is not None:
                raise RegistrationError("login_taken", "Login is already taken", 409)

            if connection.execute(
                "SELECT id FROM users WHERE phone = ?",
                (normalized_phone,),
            ).fetchone() is not None:
                raise RegistrationError("phone_in_use", "Phone is already used", 409)

            if connection.execute(
                "SELECT id FROM users WHERE registration_device_id = ?",
                (normalized_device_id,),
            ).fetchone() is not None:
                raise RegistrationError(
                    "device_already_registered",
                    "Device already has an account",
                    409,
                )

            try:
                cursor = connection.execute(
                    """
                    INSERT INTO users(
                        login,
                        password_hash,
                        role,
                        status,
                        phone,
                        registration_device_id,
                        created_at_ms,
                        updated_at_ms
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        normalized_login,
                        hash_password(password),
                        UserRole.USER.value,
                        UserStatus.ACTIVE.value,
                        normalized_phone,
                        normalized_device_id,
                        _now_ms(),
                        _now_ms(),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise RegistrationError(
                    "registration_conflict",
                    "Registration conflict detected",
                    409,
                ) from exc

            user_id = self._lastrowid(cursor)
            session = self._create_session(connection, user_id=user_id)

            user = User(
                login=normalized_login,
                role=UserRole.USER,
                status=UserStatus.ACTIVE,
                password_hash="<hidden>",
                user_id=user_id,
            )
            return AuthResult(user=user, session=session, access_mode=access_mode)

    def create_guest_session(self, *, client_kind: ClientKind) -> AuthResult:
        with self._connect() as connection:
            access_mode = self._read_access_mode(connection)
            if access_mode != AccessMode.OPEN:
                raise RegistrationError(
                    "guest_disabled_closed_mode",
                    "Guest mode is available only in open mode",
                    409,
                )

            if client_kind != ClientKind.WEB:
                raise RegistrationError(
                    "guest_only_web",
                    "Guest access is allowed only for web clients",
                    403,
                )

            guest_login = f"guest-{secrets.token_hex(6)}"
            cursor = connection.execute(
                """
                INSERT INTO users(
                    login,
                    password_hash,
                    role,
                    status,
                    phone,
                    registration_device_id,
                    created_at_ms,
                    updated_at_ms
                )
                VALUES (?, ?, ?, ?, NULL, NULL, ?, ?)
                """,
                (
                    guest_login,
                    hash_password(secrets.token_urlsafe(16)),
                    UserRole.GUEST.value,
                    UserStatus.ACTIVE.value,
                    _now_ms(),
                    _now_ms(),
                ),
            )
            user_id = self._lastrowid(cursor)

            session = self._create_session(connection, user_id=user_id)
            user = User(
                login=guest_login,
                role=UserRole.GUEST,
                status=UserStatus.ACTIVE,
                password_hash="<hidden>",
                user_id=user_id,
            )
            return AuthResult(user=user, session=session, access_mode=access_mode)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _read_access_mode(connection: sqlite3.Connection) -> AccessMode:
        row = connection.execute(
            "SELECT access_mode FROM mode_state WHERE id = 1"
        ).fetchone()
        if row is None:
            return AccessMode.CLOSED
        try:
            return AccessMode(str(row["access_mode"]))
        except ValueError:
            return AccessMode.CLOSED

    def _create_session(self, connection: sqlite3.Connection, *, user_id: int) -> SessionInfo:
        created_at_ms = _now_ms()
        expires_at_ms = created_at_ms + self._session_ttl_ms
        token = secrets.token_urlsafe(32)

        connection.execute(
            """
            INSERT INTO sessions(id, user_id, created_at_ms, expires_at_ms, revoked_at_ms)
            VALUES (?, ?, ?, ?, NULL)
            """,
            (token, user_id, created_at_ms, expires_at_ms),
        )

        return SessionInfo(
            token=token,
            user_id=user_id,
            created_at_ms=created_at_ms,
            expires_at_ms=expires_at_ms,
            revoked_at_ms=None,
        )

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        compact = "".join(ch for ch in phone.strip() if ch not in {" ", "-", "(", ")"})
        return compact

    @staticmethod
    def _normalize_device_id(device_id: str) -> str:
        return device_id.strip()

    @staticmethod
    def _is_device_blacklisted(connection: sqlite3.Connection, device_id: str) -> bool:
        try:
            row = connection.execute(
                "SELECT 1 FROM device_blacklist WHERE device_id = ?",
                (device_id,),
            ).fetchone()
        except sqlite3.OperationalError:
            return False
        return row is not None

    @staticmethod
    def _lastrowid(cursor: sqlite3.Cursor) -> int:
        value = cursor.lastrowid
        if value is None:
            raise RegistrationError("invalid_data", "lastrowid is missing", 500)
        return int(value)
