"""Server code deploy to the RPi (LC_PROJECT).

Stops local-chat-server, backs up the SQLite DB and server code, uploads the
changed server files, starts the service again and waits for /health.

Usage (PowerShell):
    $env:LC_RPI_PASS = "..."
    .venv\\Scripts\\python.exe scripts\\deploy_server_to_rpi.py
"""

import os
import sys
import time

import paramiko

HOST = os.environ.get("LC_RPI_HOST", "169.254.93.1")
USER = os.environ.get("LC_RPI_USER", "gamecat")
PASS = os.environ.get("LC_RPI_PASS")
REMOTE_ROOT = os.environ.get("LC_RPI_ROOT", "/home/gamecat/lc-server")
BACKUP_ROOT = os.environ.get("LC_RPI_BACKUPS", "/home/gamecat/backups")
LOCAL_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server"))
SERVICE = "local-chat-server"

FILES = [
    "app/models/device_pairing.py",
    "app/services/device_pairing.py",
    "app/models/__init__.py",
    "app/services/__init__.py",
    "app/api/devices.py",
    "app/api/auth.py",
    "migrations/0028_device_pair_secrets.sql",
]


def connect(attempts=6):
    last = None
    for _ in range(attempts):
        try:
            c = paramiko.SSHClient()
            c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            c.connect(HOST, username=USER, password=PASS, timeout=12, banner_timeout=12, auth_timeout=12)
            return c
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2)
    raise last


def run(c, cmd, timeout=60):
    _, out, err = c.exec_command(cmd, timeout=timeout)
    return out.read().decode("utf-8", "replace").strip(), err.read().decode("utf-8", "replace").strip()


def main():
    if not PASS:
        print("LC_RPI_PASS is not set")
        return 1

    ts = time.strftime("%Y%m%d_%H%M%S")
    c = connect()
    bdir = f"{BACKUP_ROOT}/server-{ts}"

    print("backup dir:", bdir)
    run(c, f"mkdir -p {bdir}")

    print("stopping service...")
    out, err = run(c, f"sudo -n systemctl stop {SERVICE}")
    print(" ", out or err or "stopped")

    run(c, f"cp {REMOTE_ROOT}/data/sqlite/local_chat.db {bdir}/local_chat.db 2>/dev/null; true")
    run(c, f"cp {REMOTE_ROOT}/data/sqlite/local_chat.db-wal {bdir}/local_chat.db-wal 2>/dev/null; true")
    run(c, f"cd {REMOTE_ROOT} && tar czf {bdir}/code.tgz app migrations 2>/dev/null; true")
    size, _ = run(c, f"du -sh {bdir} | cut -f1")
    print("backup size:", size)

    sftp = c.open_sftp()
    for rel in FILES:
        local = os.path.join(LOCAL_ROOT, rel.replace("/", os.sep))
        if not os.path.exists(local):
            print("MISSING local:", local)
            sftp.close()
            return 1
        sftp.put(local, f"{REMOTE_ROOT}/{rel}")
        print("uploaded:", rel)
    sftp.close()

    print("starting service...")
    out, err = run(c, f"sudo -n systemctl start {SERVICE}")
    print(" ", out or err or "started")

    ok = False
    for _ in range(20):
        time.sleep(1)
        code, _e = run(c, "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18080/health || true")
        if code.strip().endswith("200"):
            ok = True
            break
    print("health 200:", ok)
    if not ok:
        print("=== journal ===")
        j, _ = run(c, f"sudo -n journalctl -u {SERVICE} -n 40 --no-pager")
        print(j)
        return 1

    mig, _ = run(
        c,
        f"cd {REMOTE_ROOT} && ./venv/bin/python -c \"import sqlite3; "
        f"db=sqlite3.connect('data/sqlite/local_chat.db'); "
        f"print([r[0] for r in db.execute('SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 3')])\"",
    )
    print("migrations:", mig)

    checks, _ = run(c, f"grep -c 'device-challenge' {REMOTE_ROOT}/app/api/auth.py")
    print("auth.py device-challenge occurrences:", checks)

    c.close()
    print("DEPLOY_SERVER DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
