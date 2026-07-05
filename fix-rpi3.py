#!/usr/bin/env python3
"""Fix RPi: set static IP via NetworkManager, fix dnsmasq."""
import paramiko
import time

RPI_IP = "192.168.0.119"
RPI_USER = "gamecat"
RPI_PASS = "admin_pass!"


def run(client, cmd, sudo=True, timeout=15):
    full = "sudo -S " + cmd if sudo else cmd
    stdin, stdout, stderr = client.exec_command(full, timeout=timeout, get_pty=True)
    if sudo:
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

    # What network manager?
    print("=== Network backend ===")
    rc, out, err = run(client, "systemctl is-active NetworkManager 2>/dev/null; echo ---; systemctl is-active dhcpcd 2>/dev/null; echo ---; cat /etc/os-release | grep VERSION")
    print(out[:300])

    # Set static IP on wlan0 via nmcli
    print("\n=== Setting static IP via nmcli ===")
    rc, out, err = run(client, "nmcli dev status 2>&1 | grep wlan0")
    print(f"wlan0 NM status: {out[:200]}")

    # Configure wlan0 as shared (AP mode) with static IP
    rc, out, err = run(client,
        'nmcli connection add type wifi ifname wlan0 con-name LC-Hub autoconnect yes '
        'ipv4.method manual ipv4.addresses 192.168.4.1/24 '
        'ipv4.method shared 2>&1', timeout=30)
    print(f"NM add: RC={rc} {out[:200]} {err[:200]}")

    # If already exists, modify
    rc, out, err = run(client,
        'nmcli connection modify LC-Hub ipv4.method shared '
        'ipv4.addresses 192.168.4.1/24 2>&1', timeout=15)
    print(f"NM modify: RC={rc} {out[:200]} {err[:200]}")

    # Check what's on port 53
    print("\n=== Who has port 53? ===")
    rc, out, err = run(client, 'ss -tulpn | grep ":53 " || ss -tulpn | grep ":53"')
    print(f"{out[:300]}")

    # Kill systemd-resolved
    print("\n=== Disable systemd-resolved ===")
    rc, out, err = run(client,
        'systemctl stop systemd-resolved; systemctl disable systemd-resolved; '
        'systemctl mask systemd-resolved', timeout=15)
    print(f"RC={rc} {err[:200]}")

    # Verify port 53 is free
    time.sleep(1)
    rc, out, err = run(client, 'ss -tulpn | grep ":53 " || echo "PORT 53 FREE"')
    print(f"After kill: {out[:200]}")

    # Restart dnsmasq
    print("\n=== Start dnsmasq ===")
    rc, out, err = run(client, 'systemctl restart dnsmasq', timeout=10)
    print(f"RC={rc}: {err[:300]}")
    time.sleep(1)

    # Check status
    rc, out, err = run(client, 'systemctl status dnsmasq --no-pager -n 5 2>&1', timeout=10)
    print(f"Status: {out[:400]}")

    client.close()


if __name__ == "__main__":
    main()
