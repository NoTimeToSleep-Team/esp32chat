#!/usr/bin/env python3
"""Check RPi services and diagnose issues."""
import paramiko

RPI_IP = "192.168.0.119"
RPI_USER = "gamecat"
RPI_PASS = "admin_pass!"

cmds = [
    "journalctl -u dnsmasq -n 20 --no-pager 2>&1",
    "cat /etc/dnsmasq.conf",
    "cat /etc/hostapd/hostapd.conf",
    "cat /etc/dhcpcd.conf | grep -A2 'wlan0'",
    "ip a show wlan0",
    "ip a show eth0 | grep inet",
    "systemctl status hostapd --no-pager -n 10 2>&1",
    "ss -tulpn | grep -E ':53|:67|:68|:80' 2>&1",
]

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(RPI_IP, username=RPI_USER, password=RPI_PASS, timeout=10)

for cmd in cmds:
    print(f"\n=== {cmd.split('|')[0].strip()} ===")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()
    if out:
        print(out[:500])
    if err:
        print(f"ERR: {err[:200]}")

client.close()
