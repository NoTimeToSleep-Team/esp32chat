from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from time import time

from app.models import AccessMode, ClientKind, User, UserRole, UserStatus


def _now_ms() -> int:
    return int(time() * 1000)


def hash_password(password: str, *, iterations: int = 210_000) -> str:
    if not password:
        raise ValueError("Password must not be empty")
    if iterations < 100_000:
        raise ValueError("Password hash iterations must be >=100000")

    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations
    )
    return f"pbkdf2_sha256${iterations}${salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    if not password or not password_hash:
        return False

    parts = password_hash.split("$")
    if len(parts) == 4 and parts[0] == "pbkdf2_sha256":
        try:
            iterations = int(parts[1])
            salt = parts[2]
            expected = parts[3]
        except ValueError:
            return False

        candidate = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            iterations,
        ).hex()
        return hmac.compare_digest(candidate, expected)

    return hmac.compare_digest(password, password_hash)


class AuthError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class SessionInfo:
    token: str
    user_id: int
    created_at_ms: int
    expires_at_ms: int
    revoked_at_ms: int | None = None


@dataclass(frozen=True)
class AuthResult:
    user: User
    session: SessionInfo
    access_mode: AccessMode


class AuthService:
    def __init__(self, db_path: str | Path, *, session_ttl_ms: int = 86_400_000) -> None:
        self._db_path = Path(db_path)
        self._session_ttl_ms = session_ttl_ms

    def login(
        self,
        *,
        login: str,
        password: str,
        client_kind: ClientKind,
    ) -> AuthResult:
        normalized_login = login.strip()
        if not normalized_login:
            raise AuthError("invalid_credentials", "Invalid login or password", 401)

        with self._connect() as connection:
            user_row = self._read_login_row(connection, login=normalized_login)

            if user_row is None:
                raise AuthError("invalid_credentials", "Invalid login or password", 401)

            if not verify_password(password, str(user_row["password_hash"])):
                raise AuthError("invalid_credentials", "Invalid login or password", 401)

            refreshed = self._refresh_temporary_block_if_needed(
                connection,
                user_id=int(user_row["id"]),
                status_value=str(user_row["status"]),
            )
            if refreshed:
                user_row = self._read_login_row(connection, login=normalized_login)
                if user_row is None:
                    raise AuthError("invalid_credentials", "Invalid login or password", 401)

            user = self._row_to_user(user_row)
            access_mode = self._read_access_mode(connection)

            if not user.can_authenticate(
                client_kind=client_kind,
                access_mode=access_mode,
            ):
                raise AuthError(
                    "access_restricted",
                    "Authentication is not allowed for current mode/client",
                    403,
                )

            session = self._create_session(connection, user_id=int(user_row["id"]))
            return AuthResult(user=user, session=session, access_mode=access_mode)

    def logout(self, session_token: str) -> bool:
        token = session_token.strip()
        if not token:
            return False

        with self._connect() as connection:
            updated = connection.execute(
                """
                UPDATE sessions
                SET revoked_at_ms = ?
                WHERE id = ? AND revoked_at_ms IS NULL
                """,
                (_now_ms(), token),
            ).rowcount
            return updated > 0

    def get_session(
        self,
        session_token: str,
        *,
        client_kind: ClientKind,
    ) -> AuthResult:
        token = session_token.strip()
        if not token:
            raise AuthError("invalid_session", "Invalid session token", 401)

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    s.id AS session_id,
                    s.user_id,
                    s.created_at_ms,
                    s.expires_at_ms,
                    s.revoked_at_ms,
                    u.login,
                    u.password_hash,
                    u.role,
                    u.status
                FROM sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.id = ? AND s.revoked_at_ms IS NULL
                """,
                (token,),
            ).fetchone()

            if row is None:
                raise AuthError("invalid_session", "Session not found or revoked", 401)

            now_ms = _now_ms()
            if int(row["expires_at_ms"]) <= now_ms:
                connection.execute(
                    "UPDATE sessions SET revoked_at_ms = ? WHERE id = ?",
                    (now_ms, token),
                )
                raise AuthError("session_expired", "Session has expired", 401)

            refreshed = self._refresh_temporary_block_if_needed(
                connection,
                user_id=int(row["user_id"]),
                status_value=str(row["status"]),
            )
            if refreshed:
                row = connection.execute(
                    """
                    SELECT
                        s.id AS session_id,
                        s.user_id,
                        s.created_at_ms,
                        s.expires_at_ms,
                        s.revoked_at_ms,
                        u.login,
                        u.password_hash,
                        u.role,
                        u.status
                    FROM sessions s
                    JOIN users u ON u.id = s.user_id
                    WHERE s.id = ? AND s.revoked_at_ms IS NULL
                    """,
                    (token,),
                ).fetchone()
                if row is None:
                    raise AuthError("invalid_session", "Session not found or revoked", 401)

            user = self._row_to_user(row)
            access_mode = self._read_access_mode(connection)

            if not user.can_authenticate(
                client_kind=client_kind,
                access_mode=access_mode,
            ):
                raise AuthError(
                    "access_restricted",
                    "Session is not valid for current mode/client",
                    403,
                )

            session = SessionInfo(
                token=str(row["session_id"]),
                user_id=int(row["user_id"]),
                created_at_ms=int(row["created_at_ms"]),
                expires_at_ms=int(row["expires_at_ms"]),
                revoked_at_ms=None,
            )
            return AuthResult(user=user, session=session, access_mode=access_mode)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _read_login_row(connection: sqlite3.Connection, *, login: str) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT id, login, password_hash, role, status
            FROM users
            WHERE login = ?
            """,
            (login,),
        ).fetchone()

    @staticmethod
    def _refresh_temporary_block_if_needed(
        connection: sqlite3.Connection,
        *,
        user_id: int,
        status_value: str,
    ) -> bool:
        if status_value != UserStatus.BLOCKED.value:
            return False

        try:
            restriction = connection.execute(
                "SELECT blocked_until_ms FROM user_restrictions WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        except sqlite3.OperationalError:
            return False

        if restriction is None or restriction["blocked_until_ms"] is None:
            return False

        blocked_until_ms = int(restriction["blocked_until_ms"])
        now_ms = _now_ms()
        if blocked_until_ms > now_ms:
            return False

        connection.execute(
            "UPDATE users SET status = ?, updated_at_ms = ? WHERE id = ?",
            (UserStatus.ACTIVE.value, now_ms, user_id),
        )
        connection.execute(
            """
            UPDATE user_restrictions
            SET block_reason = NULL,
                blocked_until_ms = NULL,
                updated_at_ms = ?
            WHERE user_id = ?
            """,
            (now_ms, user_id),
        )
        return True

    def _read_access_mode(self, connection: sqlite3.Connection) -> AccessMode:
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
    def _row_to_user(row: sqlite3.Row) -> User:
        return User(
            login=str(row["login"]),
            role=UserRole(str(row["role"])),
            status=UserStatus(str(row["status"])),
            password_hash=str(row["password_hash"]),
            user_id=int(row["user_id"]) if "user_id" in row.keys() else int(row["id"]),
        )
