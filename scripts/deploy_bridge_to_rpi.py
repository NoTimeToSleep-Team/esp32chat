"""Deploy the LC bridge daemon to the RPi and enable its systemd service.

Usage:
    $env:LC_RPI_PASS = "..."
    .venv\\Scripts\\python.exe scripts\\deploy_bridge_to_rpi.py
"""

import os
import sys
import time

import paramiko

HOST = os.environ.get("LC_RPI_HOST", "169.254.93.1")
USER = os.environ.get("LC_RPI_USER", "gamecat")
PASS = os.environ.get("LC_RPI_PASS")
REMOTE_ROOT = os.environ.get("LC_RPI_ROOT", "/home/gamecat/lc-server")
LOCAL_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "firmware", "bridge"))
SERVICE = "lc-bridge"

FILES = [
    ("daemon/lc_bridge_daemon.py", "bridge/lc_bridge_daemon.py"),
    ("daemon/lc-bridge.service", "bridge/lc-bridge.service"),
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


def run(c, cmd, timeout=90):
    _, out, err = c.exec_command(cmd, timeout=timeout)
    return out.read().decode("utf-8", "replace").strip(), err.read().decode("utf-8", "replace").strip()


def main():
    if not PASS:
        print("LC_RPI_PASS is not set")
        return 1

    c = connect()

    run(c, f"mkdir -p {REMOTE_ROOT}/bridge")

    sftp = c.open_sftp()
    for local_rel, remote_rel in FILES:
        local = os.path.join(LOCAL_ROOT, local_rel.replace("/", os.sep))
        if not os.path.exists(local):
            print("MISSING local:", local)
            sftp.close()
            return 1
        sftp.put(local, f"{REMOTE_ROOT}/{remote_rel}")
        print("uploaded:", remote_rel)
    sftp.close()

    print("linking systemd unit...")
    out, err = run(c, f"sudo -n systemctl link {REMOTE_ROOT}/bridge/{SERVICE}.service")
    print(" ", out or err or "linked")

    run(c, "sudo -n systemctl daemon-reload")
    out, err = run(c, f"sudo -n systemctl enable --now {SERVICE}")
    print(" ", out or err or "enabled")

    time.sleep(2)
    out, err = run(c, f"sudo -n systemctl status {SERVICE} --no-pager -n 8")
    print(out or err)

    c.close()
    print("DEPLOY_BRIDGE DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
