#!/usr/bin/env python3
"""Complete RPi AP fix: bypass NM, use systemd-networkd + hostapd + dnsmasq."""
import paramiko
import time

RPI_IP = "192.168.0.119"
RPI_USER = "gamecat"
RPI_PASS = "admin_pass!"


def run(client, cmd, timeout=30):
    stdin, stdout, stderr = client.exec_command("sudo -S bash -c " + repr(cmd), timeout=timeout, get_pty=True)
    stdin.write(RPI_PASS + "\n")
    stdin.flush()
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()
    rc = stdout.channel.recv_exit_status()
    return rc, out, err


def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(RPI_IP, username=RPI_USER, password=RPI_PASS, timeout=10)

    # 1. Disable NM for wlan0
    print("[1/6] Making wlan0 unmanaged by NetworkManager...")
    rc, o, e = run(client,
        "nmcli device set wlan0 managed=no 2>/dev/null; "
        "tee /etc/NetworkManager/conf.d/99-unmanaged-wlan0.conf <<< '[keyfile]\\nunmanaged-devices=interface-name:wlan0' > /dev/null")
    print(f"  RC={rc} {e[:100] if e else 'OK'}")

    # 2. Set static IP directly
    print("[2/6] Setting static IP 192.168.4.1/24 on wlan0...")
    rc, o, e = run(client,
        "ip addr add 192.168.4.1/24 dev wlan0 2>/dev/null; "
        "ip link set wlan0 up")
    print(f"  RC={rc}")

    # 3. Create systemd service to persist IP on boot
    print("[3/6] Creating systemd service for static IP...")
    service = """[Unit]
Description=Set wlan0 static IP for LC-Hub AP
After=network.target

[Service]
Type=oneshot
ExecStart=/sbin/ip addr add 192.168.4.1/24 dev wlan0
ExecStart=/sbin/ip link set wlan0 up
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
"""
    sftp = client.open_sftp()
    with sftp.open("/tmp/wlan0-ip.service", "w") as f:
        f.write(service)
    sftp.close()
    rc, o, e = run(client,
        "cp /tmp/wlan0-ip.service /etc/systemd/system/ && "
        "systemctl daemon-reload && "
        "systemctl enable wlan0-ip.service && "
        "systemctl start wlan0-ip.service")
    print(f"  RC={rc} {e[:100] if e else 'OK'}")

    # 4. Fix dnsmasq - check what's on port 53
    print("[4/6] Checking port 53...")
    rc, o, e = run(client,
        "ss -tulpn | grep ':53 ' || echo 'PORT53_FREE'")
    print(f"  {o[:200]}")

    # 5. Stop systemd-resolved and start dnsmasq
    print("[5/6] Stopping systemd-resolved, starting dnsmasq...")
    rc, o, e = run(client,
        "systemctl stop systemd-resolved; "
        "systemctl disable systemd-resolved; "
        "systemctl mask systemd-resolved; "
        "sleep 1; "
        "systemctl start dnsmasq", timeout=20)
    print(f"  RC={rc} {e[:200] if e else 'OK'}")

    time.sleep(2)

    # 6. Verify
    print("[6/6] Verification...")
    cmds = [
        ("wlan0 IP", "ip a show wlan0 | grep 'inet '"),
        ("hostapd", "systemctl is-active hostapd"),
        ("dnsmasq", "systemctl is-active dnsmasq"),
    ]
    for label, cmd in cmds:
        rc, o, e = run(client, cmd)
        print(f"  {label}: {o[:100] if o else e[:100]}")

    print("\nDone! RPi should be AP-ready.")
    client.close()


if __name__ == "__main__":
    main()
