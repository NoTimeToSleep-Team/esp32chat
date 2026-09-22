"""Upload one server file to the RPi and restart the service (sudo -n first).

Usage: LC_RPI_PASS=... python scripts/deploy_server_file.py <local-rel-path> <remote-rel-path>
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


def run(c, cmd, timeout=60):
    _, out, err = c.exec_command(cmd, timeout=timeout)
    return out.read().decode("utf-8", "replace").strip(), err.read().decode("utf-8", "replace").strip()


def main():
    if len(sys.argv) < 3:
        print("usage: deploy_server_file.py <local-rel> <remote-rel>")
        return 1
    local_rel, remote_rel = sys.argv[1], sys.argv[2]
    local = os.path.join(LOCAL_ROOT, local_rel.replace("/", os.sep))
    if not os.path.exists(local):
        print("missing local:", local)
        return 1
    ts = time.strftime("%Y%m%d_%H%M%S")
    c = connect()
    run(c, f"mkdir -p {BACKUP_ROOT}/srv-{ts}")
    run(c, f"cp {REMOTE_ROOT}/{remote_rel} {BACKUP_ROOT}/srv-{ts}/$(basename {remote_rel}) 2>/dev/null; true")
    sftp = c.open_sftp()
    sftp.put(local, f"{REMOTE_ROOT}/{remote_rel}")
    sftp.close()
    print("uploaded:", remote_rel, "| backup:", f"{BACKUP_ROOT}/srv-{ts}")
    out, err = run(c, "sudo -n systemctl restart local-chat-server 2>&1; echo rc=$?")
    print("restart:", out or err)
    if "rc=0" not in out:
        print("NOTE: restart needs a password (no NOPASSWD sudo). Service NOT restarted.")
    time.sleep(3)
    out, _ = run(c, "systemctl is-active local-chat-server")
    print("service:", out)
    c.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
