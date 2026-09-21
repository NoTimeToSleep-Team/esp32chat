"""UI-only deploy to the RPi: app.js, app.css, index.html.

Does NOT touch server code (another agent works there). Makes a timestamped
backup of the three files first, then uploads and verifies. No service restart
is needed: static files and Jinja templates are read from disk per request.

Usage (PowerShell):
    $env:LC_RPI_PASS = "..."   # required
    .venv\\Scripts\\python.exe scripts\\deploy_ui_to_rpi.py
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

FILES = [
    "app/static/app.js",
    "app/static/app.css",
    "app/templates/index.html",
]


def connect(attempts=6):
    last = None
    for _ in range(attempts):
        try:
            c = paramiko.SSHClient()
            c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            c.connect(HOST, username=USER, password=PASS, timeout=12, banner_timeout=12, auth_timeout=12)
            return c
        except Exception as e:
            last = e
            time.sleep(2)
    raise last


def run(c, cmd, timeout=30):
    _, out, err = c.exec_command(cmd, timeout=timeout)
    return out.read().decode("utf-8", "replace").strip(), err.read().decode("utf-8", "replace").strip()


def main():
    if not PASS:
        print("LC_RPI_PASS is not set")
        return 1
    ts = time.strftime("%Y%m%d_%H%M%S")
    c = connect()
    bdir = f"{BACKUP_ROOT}/ui-{ts}"
    run(c, f"mkdir -p {bdir}")
    for rel in FILES:
        name = os.path.basename(rel)
        run(c, f"cp {REMOTE_ROOT}/{rel} {bdir}/{name} 2>/dev/null; true")
    print("backup:", bdir)

    sftp = c.open_sftp()
    for rel in FILES:
        local = os.path.join(LOCAL_ROOT, rel.replace("/", os.sep))
        if not os.path.exists(local):
            print("MISSING local:", local)
            return 1
        sftp.put(local, f"{REMOTE_ROOT}/{rel}")
        print("uploaded:", rel)
    sftp.close()

    ver, _ = run(c, f"grep -o 'v=[0-9]*' {REMOTE_ROOT}/app/templates/index.html | head -1")
    claims, _ = run(c, f"grep -c 'pair/claim' {REMOTE_ROOT}/app/static/app.js")
    print("remote index version:", ver)
    print("remote app.js pair/claim occurrences:", claims)
    c.close()
    print("DEPLOY_UI DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
