#!/usr/bin/env python3
"""Fix dnsmasq port conflict on RPi."""
import paramiko

RPI_IP = "192.168.0.119"
RPI_USER = "gamecat"
RPI_PASS = "admin_pass!"

fix_script = """#!/bin/bash
LINE="bind-interfaces"
if ! grep -q "$LINE" /etc/dnsmasq.conf; then
  echo "$LINE" >> /etc/dnsmasq.conf
fi
systemctl stop systemd-resolved 2>/dev/null || true
systemctl disable systemd-resolved 2>/dev/null || true
systemctl restart dnsmasq
systemctl restart hostapd
sleep 2
echo "hostapd: $(systemctl is-active hostapd)"
echo "dnsmasq: $(systemctl is-active dnsmasq)"
echo "wlan0: $(ip a show wlan0 | grep inet)"
echo "--- Test: nslookup google.com 127.0.0.1 ---"
nslookup google.com 127.0.0.1 2>&1 | head -5 || echo "DNS: OK (captive)"
"""

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(RPI_IP, username=RPI_USER, password=RPI_PASS, timeout=10)

sftp = client.open_sftp()
with sftp.open("/home/gamecat/fix-dnsmasq.sh", "w") as f:
    f.write(fix_script)
sftp.close()

transport = client.get_transport()
channel = transport.open_session()
channel.get_pty()
channel.exec_command("sudo bash /home/gamecat/fix-dnsmasq.sh")
channel.send(RPI_PASS + "\n")

while not channel.exit_status_ready():
    if channel.recv_ready():
        print(channel.recv(1024).decode("utf-8", errors="replace"), end="")

channel.shutdown_read()
print(f"\nExit code: {channel.recv_exit_status()}")
client.close()
