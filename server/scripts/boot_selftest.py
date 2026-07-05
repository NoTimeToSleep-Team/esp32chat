#!/usr/bin/env python3
"""
Boot self-test for RPi-Only server.
Runs on startup to verify system is healthy before accepting connections.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path


class BootTestResult:
    def __init__(self):
        self.checks: list[dict] = []
        self.all_ok = True

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append({"check": name, "ok": ok, "detail": detail})
        if not ok:
            self.all_ok = False

    def is_healthy(self) -> bool:
        return self.all_ok

    def summary(self) -> str:
        passed = sum(1 for c in self.checks if c["ok"])
        failed = sum(1 for c in self.checks if not c["ok"])
        return f"Boot self-test: {passed} passed, {failed} failed, {len(self.checks)} total"

    def to_dict(self) -> dict:
        return {
            "all_ok": self.all_ok,
            "checks": self.checks,
            "summary": self.summary(),
        }


def _get_storage_root() -> Path:
    return Path(os.environ.get("LCS_STORAGE_ROOT", "data"))


def _get_db_path() -> Path:
    url = os.environ.get("LCS_DATABASE_URL", "")
    if url.startswith("sqlite:///"):
        return Path(url[len("sqlite:///"):])
    return _get_storage_root() / "sqlite" / "local_chat.db"


def run_boot_self_test() -> BootTestResult:
    result = BootTestResult()
    storage = _get_storage_root()
    db_path = _get_db_path()

    # 1. Database integrity
    try:
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            cur = conn.execute("PRAGMA integrity_check")
            integrity = cur.fetchone()[0]
            conn.close()
            result.add("db_integrity", integrity == "ok", f"Integrity: {integrity}")
        else:
            result.add("db_exists", False, f"DB not found at {db_path} (first run?)")
    except Exception as e:
        result.add("db_check", False, str(e))

    # 2. Required directories
    for d in ["sqlite", "media", "avatars", "backups", "logs", "incidents"]:
        p = storage / d
        result.add(f"dir_{d}", p.exists() and p.is_dir(), str(p))

    # 3. Disk space
    try:
        if os.name == "posix":
            s = os.statvfs(str(storage))
            free_mb = s.f_frsize * s.f_bavail / (1024 * 1024)
        else:
            import shutil
            free_mb = shutil.disk_usage(storage).free / (1024 * 1024)
        ok = free_mb > 100
        result.add("disk_free", ok, f"{free_mb:.0f} MB free" + ("" if ok else " (< 100 MB WARNING)"))
    except Exception as e:
        result.add("disk_check", False, str(e))

    # 4. Session secret (prod check only)
    secret = os.environ.get("LCS_SESSION_SECRET", "")
    profile = os.environ.get("LCS_PROFILE", "dev")
    if profile == "prod":
        is_ok = len(secret) >= 16 and secret != "dev-insecure-change-me"
        result.add("session_secret", is_ok, f"len={len(secret)}")
    else:
        result.add("session_secret", True, f"Profile={profile} (dev mode)")

    return result


if __name__ == "__main__":
    r = run_boot_self_test()
    print(r.summary())
    for c in r.checks:
        status = "OK" if c["ok"] else "FAIL"
        print(f"  [{status}] {c['check']}: {c.get('detail', '')}")
    sys.exit(0 if r.is_healthy() else 1)
