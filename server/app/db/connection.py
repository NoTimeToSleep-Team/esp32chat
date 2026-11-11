from __future__ import annotations

import sqlite3
from pathlib import Path


DEFAULT_BUSY_TIMEOUT_MS = 5_000
DEFAULT_CACHE_SIZE_KIB = 8_192


def connect_sqlite(
    db_path: str | Path,
    *,
    read_only: bool = False,
) -> sqlite3.Connection:
    """Open a SQLite connection with the settings used by the hot paths.

    The database is already switched to WAL by the migration runner.  These
    settings are per-connection: they make concurrent readers cheap and stop
    short write bursts from failing immediately with ``database is locked``.
    """
    path = Path(db_path)
    if read_only:
        connection = sqlite3.connect(
            f"file:{path.as_posix()}?mode=ro",
            uri=True,
            timeout=DEFAULT_BUSY_TIMEOUT_MS / 1000,
        )
        connection.execute("PRAGMA query_only = ON")
    else:
        connection = sqlite3.connect(
            path,
            timeout=DEFAULT_BUSY_TIMEOUT_MS / 1000,
        )
        connection.execute("PRAGMA synchronous = NORMAL")

    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA busy_timeout = {DEFAULT_BUSY_TIMEOUT_MS}")
    connection.execute("PRAGMA temp_store = MEMORY")
    connection.execute(f"PRAGMA cache_size = -{DEFAULT_CACHE_SIZE_KIB}")
    return connection
