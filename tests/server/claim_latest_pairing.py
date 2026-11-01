"""Claim the latest pending pairing code on the RPi (hardware smoke test helper).

Reads pending codes from the server DB over SSH, then claims the newest one
through the public API as the admin user.

Usage:
    $env:LC_RPI_PASS = "..."
    .venv\\Scripts\\python.exe tests\\server\\claim_latest_pairing.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

import paramiko

RPI_HOST = os.environ.get("LC_RPI_HOST", "169.254.93.1")
RPI_USER = os.environ.get("LC_RPI_USER", "gamecat")
RPI_PASS = os.environ.get("LC_RPI_PASS")
RPI_ROOT = os.environ.get("LC_RPI_ROOT", "/opt/local-chat-server")
BASE = os.environ.get("LC_BASE", "http://169.254.93.1:18080")
ADMIN_LOGIN = os.environ.get("LC_ADMIN_LOGIN", "admin")
ADMIN_PASSWORD = os.environ.get("LC_ADMIN_PASSWORD", "")

REMOTE_QUERY = """cd {root} && ./venv/bin/python3 - <<'PYEOF'
import sqlite3
db = sqlite3.connect('data/sqlite/local_chat.db')
rows = list(db.execute(
    "SELECT device_id, code FROM device_pair_requests WHERE status='pending' ORDER BY created_at_ms DESC LIMIT 5"
))
for device_id, code in rows:
    print(f"{device_id} {code}")
PYEOF"""


def request(method: str, path: str, payload: dict | None = None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        BASE + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = {"raw": body}
        return exc.code, parsed


def main() -> int:
    if not RPI_PASS:
        print("LC_RPI_PASS is not set")
        return 1

    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(RPI_HOST, username=RPI_USER, password=RPI_PASS, timeout=12)
    _, out, err = c.exec_command(REMOTE_QUERY.replace("{root}", RPI_ROOT), timeout=25)
    data = out.read().decode("utf-8", "replace").strip()
    errors = err.read().decode("utf-8", "replace").strip()
    c.close()

    if not data:
        print("no pending pairing codes found")
        if errors:
            print("ssh stderr:", errors[:300])
        return 1

    rows = [line.split() for line in data.splitlines() if len(line.split()) == 2]
    print("pending codes:", rows)
    device_id, code = rows[0]

    status, body = request(
        "POST",
        "/auth/login",
        {"login": ADMIN_LOGIN, "password": ADMIN_PASSWORD, "client_kind": "web"},
    )
    token = str(body.get("session", {}).get("token", "")) if isinstance(body, dict) else ""
    if status != 200 or not token:
        print("login failed:", status, str(body)[:200])
        return 1

    status, body = request(
        "POST",
        "/devices/api/pair/claim",
        {"session_token": token, "code": code},
    )
    print("claim:", status, str(body)[:300])
    if status != 200:
        return 1

    status, body = request("GET", f"/devices/api/pair/status?device_id={device_id}")
    print("pair status:", status, str(body)[:200])
    return 0


if __name__ == "__main__":
    sys.exit(main())
