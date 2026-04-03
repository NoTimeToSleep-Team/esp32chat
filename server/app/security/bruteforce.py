from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from time import time


def _now_ms() -> int:
    return int(time() * 1000)


@dataclass(frozen=True)
class BruteForceDecision:
    allowed: bool
    blocked_until_ms: int | None


class BruteForceGuard:
    def __init__(
        self,
        db_path: str | Path,
        *,
        window_ms: int,
        login_attempt_limit: int,
        ip_attempt_limit: int,
        block_ms: int,
    ) -> None:
        self._db_path = Path(db_path)
        self._window_ms = window_ms
        self._login_attempt_limit = login_attempt_limit
        self._ip_attempt_limit = ip_attempt_limit
        self._block_ms = block_ms

    def check_allowed(self, *, ip_address: str) -> BruteForceDecision:
        now_ms = _now_ms()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT blocked_until_ms
                FROM ip_blocks
                WHERE ip_address = ?
                """,
                (ip_address,),
            ).fetchone()

            if row is None:
                return BruteForceDecision(allowed=True, blocked_until_ms=None)

            blocked_until_ms = int(row["blocked_until_ms"])
            if blocked_until_ms <= now_ms:
                connection.execute(
                    "DELETE FROM ip_blocks WHERE ip_address = ?",
                    (ip_address,),
                )
                return BruteForceDecision(allowed=True, blocked_until_ms=None)

            return BruteForceDecision(allowed=False, blocked_until_ms=blocked_until_ms)

    def record_attempt(
        self,
        *,
        login: str,
        ip_address: str,
        success: bool,
    ) -> int | None:
        normalized_login = login.strip().lower()
        now_ms = _now_ms()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO auth_attempts(login, ip_address, success, created_at_ms)
                VALUES (?, ?, ?, ?)
                """,
                (normalized_login, ip_address, 1 if success else 0, now_ms),
            )

            if success:
                return None

            boundary = now_ms - self._window_ms

            login_failed_count = int(
                connection.execute(
                    """
                    SELECT COUNT(*) AS total
                    FROM auth_attempts
                    WHERE login = ? AND success = 0 AND created_at_ms >= ?
                    """,
                    (normalized_login, boundary),
                ).fetchone()["total"]
            )

            ip_failed_count = int(
                connection.execute(
                    """
                    SELECT COUNT(*) AS total
                    FROM auth_attempts
                    WHERE ip_address = ? AND success = 0 AND created_at_ms >= ?
                    """,
                    (ip_address, boundary),
                ).fetchone()["total"]
            )

            if (
                login_failed_count >= self._login_attempt_limit
                or ip_failed_count >= self._ip_attempt_limit
            ):
                blocked_until_ms = now_ms + self._block_ms
                connection.execute(
                    """
                    INSERT INTO ip_blocks(ip_address, blocked_until_ms, reason, created_at_ms, updated_at_ms)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(ip_address) DO UPDATE SET
                        blocked_until_ms = excluded.blocked_until_ms,
                        reason = excluded.reason,
                        updated_at_ms = excluded.updated_at_ms
                    """,
                    (
                        ip_address,
                        blocked_until_ms,
                        "auth_bruteforce_guard",
                        now_ms,
                        now_ms,
                    ),
                )
                return blocked_until_ms

            return None

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection
