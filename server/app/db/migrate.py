from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from time import time


@dataclass(frozen=True)
class MigrationResult:
    database_path: Path
    applied_versions: tuple[str, ...]
    discovered_versions: tuple[str, ...]


def _server_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _migrations_root() -> Path:
    return _server_root() / "migrations"


def _extract_sqlite_path(database_url: str) -> Path:
    if not database_url.startswith("sqlite:///"):
        raise ValueError("Only sqlite:/// URLs are supported at this stage")

    raw = database_url[len("sqlite:///") :].split("?", 1)[0]
    if not raw:
        raise ValueError("Database URL must include a path")

    if raw.startswith("/") and len(raw) >= 3 and raw[2] == ":":
        raw = raw[1:]

    db_path = Path(raw)
    if not db_path.is_absolute():
        db_path = (_server_root() / db_path).resolve()
    return db_path


def _ensure_migrations_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at_ms INTEGER NOT NULL
        )
        """
    )


def apply_sql_migrations(database_url: str) -> MigrationResult:
    db_path = _extract_sqlite_path(database_url)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    migrations_dir = _migrations_root()
    migration_files = sorted(migrations_dir.glob("*.sql"))
    discovered_versions = tuple(path.name for path in migration_files)

    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA foreign_keys = ON")

    try:
        _ensure_migrations_table(connection)

        existing_rows = connection.execute(
            "SELECT version FROM schema_migrations"
        ).fetchall()
        applied_set = {row[0] for row in existing_rows}

        applied_versions: list[str] = []

        for migration_file in migration_files:
            version = migration_file.name
            if version in applied_set:
                continue

            sql_script = migration_file.read_text(encoding="utf-8")
            try:
                connection.execute("BEGIN")
                connection.executescript(sql_script)
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at_ms) VALUES (?, ?)",
                    (version, int(time() * 1000)),
                )
                connection.commit()
                applied_versions.append(version)
            except Exception:
                connection.rollback()
                raise
    finally:
        connection.close()

    return MigrationResult(
        database_path=db_path,
        applied_versions=tuple(applied_versions),
        discovered_versions=discovered_versions,
    )
