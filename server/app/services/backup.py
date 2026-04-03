from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from time import time
from typing import cast

from app.models import BackupRecord, BackupRestorePlan, BackupStatus, UserRole, UserStatus


def _now_ms() -> int:
    return int(time() * 1000)


@dataclass(frozen=True)
class BackupError(RuntimeError):
    code: str
    message: str
    status_code: int

    def __str__(self) -> str:
        return self.message


class BackupService:
    def __init__(self, db_path: str | Path, storage_root: str | Path) -> None:
        self._db_path = Path(db_path)
        self._storage_root = Path(storage_root)
        self._backups_root = self._storage_root / "backups"

    def list_backups(self, *, actor_user_id: int, limit: int = 100, offset: int = 0) -> list[BackupRecord]:
        safe_limit = min(max(limit, 1), 500)
        safe_offset = max(offset, 0)

        with self._connect() as connection:
            self._require_active_admin(connection, actor_user_id)
            rows = connection.execute(
                """
                SELECT *
                FROM ops_backup_history
                ORDER BY created_at_ms DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (safe_limit, safe_offset),
            ).fetchall()
            return [self._row_to_backup(row) for row in rows]

    def create_backup(
        self,
        *,
        actor_user_id: int,
        reason: str | None = None,
        dry_run: bool = False,
    ) -> BackupRecord:
        now_ms = _now_ms()
        backup_name = f"backup_{now_ms}.sqlite3"
        backup_path = (self._backups_root / backup_name).resolve()
        normalized_reason = (reason or "").strip() or None
        source_exists = self._db_path.exists()

        with self._connect() as connection:
            self._require_active_admin(connection, actor_user_id)

            if not source_exists:
                raise BackupError("database_not_found", "Database file was not found", 500)

            if dry_run:
                size_bytes = self._db_path.stat().st_size
                row_id = self._insert_backup_row(
                    connection,
                    backup_name=backup_name,
                    backup_path=backup_path,
                    status=BackupStatus.DRY_RUN,
                    reason=normalized_reason,
                    actor_user_id=actor_user_id,
                    created_at_ms=now_ms,
                    completed_at_ms=now_ms,
                    size_bytes=size_bytes,
                    checksum_sha256=None,
                    error_message=None,
                )
                row = connection.execute(
                    "SELECT * FROM ops_backup_history WHERE id = ?",
                    (row_id,),
                ).fetchone()
                if row is None:
                    raise BackupError("backup_create_failed", "Failed to create backup entry", 500)
                return self._row_to_backup(row)

            try:
                self._backups_root.mkdir(parents=True, exist_ok=True)
                self._copy_sqlite_database(self._db_path, backup_path)
                checksum = self._sha256(backup_path)
                size_bytes = backup_path.stat().st_size
                row_id = self._insert_backup_row(
                    connection,
                    backup_name=backup_name,
                    backup_path=backup_path,
                    status=BackupStatus.COMPLETED,
                    reason=normalized_reason,
                    actor_user_id=actor_user_id,
                    created_at_ms=now_ms,
                    completed_at_ms=_now_ms(),
                    size_bytes=size_bytes,
                    checksum_sha256=checksum,
                    error_message=None,
                )
            except Exception as exc:
                self._insert_backup_row(
                    connection,
                    backup_name=backup_name,
                    backup_path=backup_path,
                    status=BackupStatus.FAILED,
                    reason=normalized_reason,
                    actor_user_id=actor_user_id,
                    created_at_ms=now_ms,
                    completed_at_ms=_now_ms(),
                    size_bytes=None,
                    checksum_sha256=None,
                    error_message=str(exc),
                )
                raise BackupError("backup_create_failed", "Failed to create backup file", 500) from exc

            row = connection.execute(
                "SELECT * FROM ops_backup_history WHERE id = ?",
                (row_id,),
            ).fetchone()
            if row is None:
                raise BackupError("backup_create_failed", "Failed to load backup record", 500)
            return self._row_to_backup(row)

    def restore_dry_run(
        self,
        *,
        actor_user_id: int,
        backup_name: str,
    ) -> BackupRestorePlan:
        normalized_name = backup_name.strip()
        if not normalized_name:
            raise BackupError("invalid_backup_name", "Backup name must not be empty", 422)

        with self._connect() as connection:
            self._require_active_admin(connection, actor_user_id)
            row = connection.execute(
                """
                SELECT backup_name, backup_path
                FROM ops_backup_history
                WHERE backup_name = ?
                  AND status = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (normalized_name, BackupStatus.COMPLETED.value),
            ).fetchone()
            if row is None:
                raise BackupError("backup_not_found", "Backup record was not found", 404)

            backup_path = Path(str(row["backup_path"]))
            if not backup_path.exists():
                raise BackupError("backup_file_missing", "Backup file is missing on disk", 404)

            return BackupRestorePlan(
                backup_name=str(row["backup_name"]),
                backup_path=str(backup_path),
                database_path=str(self._db_path),
                backup_size_bytes=backup_path.stat().st_size,
                dry_run=True,
            )

    def _insert_backup_row(
        self,
        connection: sqlite3.Connection,
        *,
        backup_name: str,
        backup_path: Path,
        status: BackupStatus,
        reason: str | None,
        actor_user_id: int,
        created_at_ms: int,
        completed_at_ms: int,
        size_bytes: int | None,
        checksum_sha256: str | None,
        error_message: str | None,
    ) -> int:
        cursor = connection.execute(
            """
            INSERT INTO ops_backup_history(
                backup_name,
                backup_path,
                status,
                reason,
                trigger_kind,
                actor_user_id,
                created_at_ms,
                completed_at_ms,
                size_bytes,
                checksum_sha256,
                error_message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                backup_name,
                str(backup_path),
                status.value,
                reason,
                "manual",
                actor_user_id,
                created_at_ms,
                completed_at_ms,
                size_bytes,
                checksum_sha256,
                error_message,
            ),
        )
        row_id = cursor.lastrowid
        if row_id is None:
            raise BackupError("backup_insert_failed", "Failed to write backup history", 500)
        return cast(int, row_id)

    @staticmethod
    def _copy_sqlite_database(source_path: Path, target_path: Path) -> None:
        source = sqlite3.connect(source_path)
        target = sqlite3.connect(target_path)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _row_to_backup(row: sqlite3.Row) -> BackupRecord:
        return BackupRecord(
            backup_id=int(row["id"]),
            backup_name=str(row["backup_name"]),
            backup_path=str(row["backup_path"]),
            status=BackupStatus(str(row["status"])),
            reason=str(row["reason"]) if row["reason"] is not None else None,
            trigger_kind=str(row["trigger_kind"]),
            actor_user_id=int(row["actor_user_id"]) if row["actor_user_id"] is not None else None,
            created_at_ms=int(row["created_at_ms"]),
            completed_at_ms=int(row["completed_at_ms"]) if row["completed_at_ms"] is not None else None,
            size_bytes=int(row["size_bytes"]) if row["size_bytes"] is not None else None,
            checksum_sha256=str(row["checksum_sha256"]) if row["checksum_sha256"] is not None else None,
            error_message=str(row["error_message"]) if row["error_message"] is not None else None,
        )

    @staticmethod
    def _require_active_admin(connection: sqlite3.Connection, actor_user_id: int) -> None:
        row = connection.execute(
            "SELECT role, status FROM users WHERE id = ?",
            (actor_user_id,),
        ).fetchone()
        if row is None:
            raise BackupError("actor_not_found", "Actor user was not found", 404)

        role = str(row["role"])
        status = str(row["status"])
        if role != UserRole.ADMIN.value:
            raise BackupError("admin_only", "Admin role is required", 403)
        if status != UserStatus.ACTIVE.value:
            raise BackupError("actor_inactive", "Admin account is not active", 403)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection
