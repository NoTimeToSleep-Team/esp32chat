#!/usr/bin/env python3
"""Deploy LC server and setup AP on RPi 5 via SSH."""
import paramiko
import os
import time
import sys
import stat

RPI_IP = "192.168.0.119"
RPI_USER = "gamecat"
RPI_PASS = "admin_pass!"
SERVER_DIR = r"D:\project\server"
PROJECT_DIR = r"D:\project"


class RPiDeployer:
    def __init__(self, host, user, password):
        self.host = host
        self.user = user
        self.password = password
        self.client = None
        self.sftp = None

    def connect(self):
        print(f"Connecting to {self.user}@{self.host}...")
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(self.host, username=self.user, password=self.password, timeout=15)
        self.sftp = self.client.open_sftp()
        print("  Connected OK")

    def exec(self, cmd, sudo=False, timeout=30):
        full_cmd = f"sudo {cmd}" if sudo else cmd
        print(f"  $ {full_cmd}")
        stdin, stdout, stderr = self.client.exec_command(full_cmd, timeout=timeout)
        if sudo:
            stdin.write(self.password + "\n")
            stdin.flush()
        exit_code = stdout.channel.recv_exit_status()
        out = stdout.read().decode().strip()
        err = stderr.read().decode().strip()
        if out:
            for line in out.split("\n"):
                print(f"    {line}")
        if err and exit_code != 0:
            print(f"  ERR: {err}")
        return exit_code, out, err

    def close(self):
        if self.sftp:
            self.sftp.close()
        if self.client:
            self.client.close()


def copy_server(deployer):
    """Copy server directory (excluding server.json) to RPi."""
    print("\n=== Copying server files ===")
    rpi_path = "/home/gamecat/lc-server"
    deployer.exec(f"mkdir -p {rpi_path}")

    # Create dirs first
    for root, dirs, files in os.walk(SERVER_DIR):
        rel = os.path.relpath(root, SERVER_DIR)
        target = os.path.join(rpi_path, rel).replace("\\", "/")
        if rel == ".":
            continue
        try:
            deployer.sftp.stat(target)
        except FileNotFoundError:
            deployer.sftp.mkdir(target)
            print(f"  mkdir {target}")

    # Copy files (exclude server.json)
    count = 0
    for root, dirs, files in os.walk(SERVER_DIR):
        rel = os.path.relpath(root, SERVER_DIR)
        for f in files:
            if f == "server.json":
                continue
            local = os.path.join(root, f)
            target = os.path.join(rpi_path, rel, f).replace("\\", "/") if rel != "." else os.path.join(rpi_path, f).replace("\\", "/")
            try:
                deployer.sftp.put(local, target)
                count += 1
                if count % 20 == 0:
                    print(f"  Copied {count} files...")
            except Exception as e:
                print(f"  SKIP {f}: {e}")
    print(f"  Copied {count} files total")


def copy_scripts(deployer):
    """Copy setup scripts to RPi."""
    print("\n=== Copying setup scripts ===")
    files = ["rpi-setup.sh", "rpi-deploy-server.sh",
             "server/scripts/seed_test_users.py"]
    for f in files:
        local = os.path.join(PROJECT_DIR, f)
        if os.path.exists(local):
            deployer.sftp.put(local, f"/home/gamecat/{os.path.basename(f)}")
            print(f"  Copied {f}")
    deployer.exec("chmod +x ~/rpi-setup.sh ~/rpi-deploy-server.sh")


def phase1_setup_rpi(deployer):
    """Run RPi AP setup script."""
    print("\n=== Phase 1: RPi AP Setup ===")
    deployer.exec("~/rpi-setup.sh", sudo=True, timeout=120)


def phase2_deploy_server():
    """Connect to RPi after reboot (192.168.4.1) and deploy server."""
    print("\n=== Phase 2: Server Deploy ===")
    print("Waiting 60s for RPi to reboot...")
    time.sleep(60)

    ap_deployer = RPiDeployer("192.168.4.1", RPI_USER, RPI_PASS)
    try:
        ap_deployer.connect()
    except Exception as e:
        print(f"  Waiting more... ({e})")
        time.sleep(30)
        ap_deployer.connect()

    print("Running server deploy script...")
    ap_deployer.exec("~/rpi-deploy-server.sh", timeout=180)

    print("\n=== Verification ===")
    code, out, _ = ap_deployer.exec("curl -s http://192.168.4.1:18080/health", timeout=10)
    if code == 0 and out:
        print(f"  Server health: {out[:200]}")
        print("\n  ✅ Server is running!")
    else:
        print("  ❌ Server health check failed")

    ap_deployer.close()


def main():
    print("=" * 50)
    print("RPi Deployment: LC-Hub AP + Server")
    print("=" * 50)

    # Phase 1: Pre-reboot
    deployer = RPiDeployer(RPI_IP, RPI_USER, RPI_PASS)
    try:
        deployer.connect()
        copy_server(deployer)
        copy_scripts(deployer)
        phase1_setup_rpi(deployer)

        print("\n=== Rebooting RPi ===")
        deployer.exec("reboot", sudo=True, timeout=5)
    except Exception as e:
        print(f"  Error: {e}")
    finally:
        deployer.close()

    # Phase 2: Post-reboot (need user to connect to LC-Hub Wi-Fi)
    print("\n" + "=" * 50)
    print("PHASE 1 COMPLETE: RPi is rebooting")
    print("=" * 50)
    print("\nNEXT STEP:")
    print("1. Disconnect Ethernet from PC (or disable it)")
    print("2. Connect PC Wi-Fi to 'LC-Hub' (open network)")
    print("3. After PC gets 192.168.4.x IP, run phase2:")
    print("   python deploy-rpi.py --phase2\n")

    if "--phase2" in sys.argv:
        phase2_deploy_server()


if __name__ == "__main__":
    if "--phase2" in sys.argv:
        phase2_deploy_server()
    else:
        main()
