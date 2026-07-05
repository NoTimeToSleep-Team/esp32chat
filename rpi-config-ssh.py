#!/usr/bin/env python3
"""Configure RPi: hostapd + dnsmasq + iptables via SSH."""
import paramiko
import sys

RPI_IP = "192.168.0.119"
RPI_USER = "gamecat"
RPI_PASS = "admin_pass!"


def ssh(cmd, sudo=False):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(RPI_IP, username=RPI_USER, password=RPI_PASS, timeout=15)
    full = f"sudo bash -c '{cmd}'" if sudo else cmd
    stdin, stdout, stderr = client.exec_command(full, timeout=60)
    if sudo:
        stdin.write(RPI_PASS + "\n")
        stdin.flush()
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    rc = stdout.channel.recv_exit_status()
    client.close()
    return rc, out, err


def write_file(path, content, sudo=False):
    """Write content to file via SSH."""
    tmp = "/tmp/_cfg"
    # First write locally, then sudo mv
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(RPI_IP, username=RPI_USER, password=RPI_PASS, timeout=15)
    
    # Write via sftp to temp
    sftp = client.open_sftp()
    with sftp.open(tmp, "w") as f:
        f.write(content)
    sftp.close()
    
    # Move to target
    if sudo:
        stdin, stdout, stderr = client.exec_command(f"sudo mv {tmp} {path} && sudo chmod 644 {path}", timeout=10)
        stdin.write(RPI_PASS + "\n")
        stdin.flush()
    else:
        stdin, stdout, stderr = client.exec_command(f"mv {tmp} {path}", timeout=10)
    stdout.channel.recv_exit_status()
    client.close()


def main():
    print("Configuring RPi...")

    # 1. Hostapd config
    print("[1/5] Writing hostapd.conf...")
    write_file("/etc/hostapd/hostapd.conf", """interface=wlan0
driver=nl80211
ssid=LC-Hub
hw_mode=g
channel=6
auth_algs=1
wmm_enabled=0
""", sudo=True)

    # 2. Enable hostapd
    print("[2/5] Enabling hostapd...")
    rc, o, e = ssh("systemctl unmask hostapd && systemctl enable hostapd", sudo=True)
    print(o, e)

    # 3. Dnsmasq config
    print("[3/5] Writing dnsmasq.conf...")
    write_file("/etc/dnsmasq.conf", """interface=wlan0
dhcp-range=192.168.4.2,192.168.4.50,255.255.255.0,24h
dhcp-option=3,192.168.4.1
dhcp-option=6,192.168.4.1
address=/#/192.168.4.1
server=8.8.8.8
no-hosts
""", sudo=True)

    rc, o, e = ssh("systemctl enable dnsmasq", sudo=True)
    print(o, e)

    # 4. Static IP for wlan0
    print("[4/5] Setting static IP...")
    rc, o, e = ssh("grep -q 'interface wlan0' /etc/dhcpcd.conf || echo -e '\\ninterface wlan0\\nstatic ip_address=192.168.4.1/24\\nnohook wpa_supplicant' >> /etc/dhcpcd.conf", sudo=True)
    print(o, e)

    # 5. iptables redirect
    print("[5/5] Adding iptables rule...")
    rc, o, e = ssh("iptables -t nat -C PREROUTING -i wlan0 -p tcp --dport 80 -j REDIRECT --to-port 18080 2>/dev/null || iptables -t nat -A PREROUTING -i wlan0 -p tcp --dport 80 -j REDIRECT --to-port 18080; netfilter-persistent save", sudo=True)
    print(o, e)

    print("\n✅ Configuration complete!")
    print("Check: cat /etc/hostapd/hostapd.conf")
    print("Check: cat /etc/dnsmasq.conf")
    print("\nNow run: sudo reboot")


if __name__ == "__main__":
    main()
