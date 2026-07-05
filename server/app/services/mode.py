from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from time import time

from app.models import AccessMode


def _now_ms() -> int:
    return int(time() * 1000)


@dataclass(frozen=True)
class ModeError(RuntimeError):
    code: str
    message: str
    status_code: int

    def __str__(self) -> str:
        return self.message


class ModeService:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)

    def get_mode(self) -> AccessMode:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT access_mode FROM mode_state WHERE id = 1"
            ).fetchone()
            if row is None:
                return AccessMode.CLOSED
            try:
                return AccessMode(str(row["access_mode"]))
            except ValueError:
                return AccessMode.CLOSED

    def set_mode(self, access_mode: AccessMode) -> AccessMode:
        with self._connect() as connection:
            now_ms = _now_ms()
            connection.execute(
                """
                INSERT INTO mode_state(id, access_mode, updated_at_ms)
                VALUES (1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    access_mode = excluded.access_mode,
                    updated_at_ms = excluded.updated_at_ms
                """,
                (access_mode.value, now_ms),
            )
            row = connection.execute(
                "SELECT access_mode FROM mode_state WHERE id = 1"
            ).fetchone()
            if row is None:
                raise ModeError("mode_update_failed", "Failed to update mode", 500)

            try:
                return AccessMode(str(row["access_mode"]))
            except ValueError as exc:
                raise ModeError("invalid_mode_state", "Stored mode is invalid", 500) from exc

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection
