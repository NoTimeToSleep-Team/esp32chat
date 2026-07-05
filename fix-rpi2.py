#!/usr/bin/env python3
"""Fix RPi: assign IP to wlan0, fix dnsmasq port 53 conflict."""
import paramiko
import time

RPI_IP = "192.168.0.119"
RPI_USER = "gamecat"
RPI_PASS = "admin_pass!"


def run(client, cmd, sudo=False, timeout=15):
    if sudo:
        cmd = "sudo -S " + cmd
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout, get_pty=True)
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

    # Check what's using port 53 now
    print("=== Port 53 check ===")
    rc, out, err = run(client, "ss -tulpn | grep ':53 '", sudo=True)
    print(f"OUT: {out[:300] if out else '(none)'}")
    print(f"ERR: {err[:200] if err else '(none)'}")

    # Check what's using port 67 (DHCP)
    print("=== Port 67 check ===")
    rc, out, err = run(client, "ss -tulpn | grep ':67 '", sudo=True)
    print(f"OUT: {out[:300] if out else '(none)'}")

    # Force kill process on port 53
    print("=== Force freeing port 53 ===")
    rc, out, err = run(client, "fuser -k 53/tcp 53/udp 2>/dev/null; echo done", sudo=True)
    print(f"OUT: {out[:100] if out else '(none)'}")

    # Restart dhcpcd to get IP on wlan0
    print("=== Restart dhcpcd ===")
    rc, out, err = run(client, "systemctl restart dhcpcd", sudo=True)
    print(f"RC={rc} OUT: {out[:100] if out else '(none)'}")

    time.sleep(3)

    # Check wlan0 IP
    print("=== wlan0 IP ===")
    rc, out, err = run(client, "ip a show wlan0 | grep inet")
    print(f"OUT: {out[:100] if out else 'NO IP!'}")

    # Start dnsmasq
    print("=== Start dnsmasq ===")
    rc, out, err = run(client, "systemctl start dnsmasq", sudo=True)
    print(f"RC={rc}: {out[:100] if out else '(none)'} {err[:200] if err else ''}")

    time.sleep(1)

    # Check dnsmasq status
    print("=== dnsmasq status ===")
    rc, out, err = run(client, "systemctl is-active dnsmasq")
    print(f"dnsmasq: {out[:50] if out else err[:50]}")

    # Final status
    print("=== FINAL STATUS ===")
    rc, out, err = run(client, "ip a show wlan0 | grep inet")
    print(f"wlan0: {out[:100] if out else 'NO IP!'}")
    rc, out, err = run(client, "systemctl is-active hostapd")
    print(f"hostapd: {out}")
    rc, out, err = run(client, "systemctl is-active dnsmasq")
    print(f"dnsmasq: {out}")

    client.close()


if __name__ == "__main__":
    main()
