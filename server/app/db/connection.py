from __future__ import annotations

import sqlite3
from pathlib import Path


DEFAULT_BUSY_TIMEOUT_MS = 5_000
DEFAULT_CACHE_SIZE_KIB = 8_192


class ClosingConnection(sqlite3.Connection):
    """SQLite connection that also closes on ``with`` exit.

    ``sqlite3.Connection.__exit__`` commits or rolls back, but deliberately
    leaves the handle open.  Every service in this project uses
    ``with self._connect() as connection:`` as its request scope, so the
    close step belongs here to avoid leaking one file descriptor per request.
    """

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def connect_sqlite(
    db_path: str | Path,
    *,
    read_only: bool = False,
    timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
) -> sqlite3.Connection:
    """Open a SQLite connection with the settings used by the hot paths.

    The returned connection is a :class:`ClosingConnection`: using it as a
    context manager commits/rolls back and closes the file handle.  The
    database itself is already switched to WAL by the migration runner.
    """
    path = Path(db_path)
    timeout_seconds = max(int(timeout_ms), 1) / 1000
    connection: sqlite3.Connection | None = None
    try:
        if read_only:
            connection = sqlite3.connect(
                f"file:{path.as_posix()}?mode=ro",
                uri=True,
                timeout=timeout_seconds,
                factory=ClosingConnection,
            )
            connection.execute("PRAGMA query_only = ON")
        else:
            connection = sqlite3.connect(
                path,
                timeout=timeout_seconds,
                factory=ClosingConnection,
            )
            connection.execute("PRAGMA synchronous = NORMAL")

        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {max(int(timeout_ms), 1)}")
        connection.execute("PRAGMA temp_store = MEMORY")
        connection.execute(f"PRAGMA cache_size = -{DEFAULT_CACHE_SIZE_KIB}")
        return connection
    except Exception:
        # A failed PRAGMA must not leave a half-configured descriptor behind.
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass
        raise
