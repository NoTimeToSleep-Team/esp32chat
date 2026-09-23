"""Deploy chat-related server files to the RPi with a single service restart.

Usage (PowerShell):
    $env:LC_RPI_PASS = "..."
    .venv\\Scripts\\python.exe scripts\\deploy_chat_to_rpi.py app/services/chat.py app/api/chat.py

Files are given relative to the local `server/` directory (same as deploy_server_file.py).
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
    files = sys.argv[1:]
    if not files:
        print("usage: deploy_chat_to_rpi.py <local-rel> [<local-rel> ...]")
        return 1
    if not PASS:
        print("LC_RPI_PASS is not set")
        return 1

    for rel in files:
        local = os.path.join(LOCAL_ROOT, rel.replace("/", os.sep))
        if not os.path.exists(local):
            print("missing local:", local)
            return 1

    ts = time.strftime("%Y%m%d_%H%M%S")
    c = connect()
    bdir = f"{BACKUP_ROOT}/chat-{ts}"
    run(c, f"mkdir -p {bdir}")

    for rel in files:
        run(c, f"cp {REMOTE_ROOT}/{rel} {bdir}/$(echo {rel} | tr '/' '_') 2>/dev/null; true")

    sftp = c.open_sftp()
    for rel in files:
        local = os.path.join(LOCAL_ROOT, rel.replace("/", os.sep))
        sftp.put(local, f"{REMOTE_ROOT}/{rel}")
        print("uploaded:", rel)
    sftp.close()

    out, err = run(c, f"sudo -n systemctl restart {SERVICE} 2>&1; echo rc=$?")
    print("restart:", out or err)

    ok = False
    for _ in range(25):
        time.sleep(1)
        code, _e = run(c, "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18080/health || true")
        if code.strip().endswith("200"):
            ok = True
            break
    print("health 200:", ok)
    if not ok:
        j, _ = run(c, f"sudo -n journalctl -u {SERVICE} -n 40 --no-pager")
        print(j)
        c.close()
        return 1

    mig, _ = run(
        c,
        f"cd {REMOTE_ROOT} && ./venv/bin/python -c \"import sqlite3; "
        f"db=sqlite3.connect('data/sqlite/local_chat.db'); "
        f"print([r[0] for r in db.execute('SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 3')])\"",
    )
    print("migrations:", mig)
    c.close()
    print("DEPLOY_CHAT DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
