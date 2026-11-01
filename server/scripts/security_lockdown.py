"""One-shot containment for leaked debug logs and sessions.

Run once after deploying a security fix, not on every service start:

    python3 server/scripts/security_lockdown.py --db data/sqlite/local_chat.db

The script backs up the database first, deletes debug events (which may contain
session tokens), and revokes all active sessions.  It intentionally does not
change user passwords.
"""
from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from time import time


def _now_ms() -> int:
    return int(time() * 1000)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/sqlite/local_chat.db")
    parser.add_argument("--backup-dir", default="/tmp")
    parser.add_argument("--keep-sessions", action="store_true")
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    if not db_path.exists():
        raise SystemExit(f"database not found: {db_path}")

    backup_dir = Path(args.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = backup_dir / f"local_chat-security-{stamp}.db"

    source = sqlite3.connect(db_path)
    target = sqlite3.connect(backup_path)
    try:
        source.backup(target)
    finally:
        target.close()
    backup_path.chmod(0o600)
    print(f"backup: {backup_path}")

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        debug_count = connection.execute("SELECT COUNT(*) AS n FROM debug_events").fetchone()["n"]
        connection.execute("DELETE FROM debug_events")
        revoked = 0
        if not args.keep_sessions:
            revoked = connection.execute(
                "UPDATE sessions SET revoked_at_ms = ? WHERE revoked_at_ms IS NULL",
                (_now_ms(),),
            ).rowcount
        connection.commit()
    finally:
        connection.close()

    print(f"debug_events deleted: {debug_count}")
    print(f"sessions revoked: {revoked}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
