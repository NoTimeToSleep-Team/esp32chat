#!/bin/bash
set -e

echo "[1/6] Making wlan0 unmanaged by NetworkManager..."
nmcli device set wlan0 managed=no 2>/dev/null || true
cat > /etc/NetworkManager/conf.d/99-unmanaged-wlan0.conf << 'EOF'
[keyfile]
unmanaged-devices=interface-name:wlan0
EOF

echo "[2/6] Setting static IP 192.168.4.1/24 on wlan0..."
ip addr add 192.168.4.1/24 dev wlan0 2>/dev/null || true
ip link set wlan0 up

echo "[3/6] Creating systemd service for static IP..."
cat > /etc/systemd/system/wlan0-ip.service << 'SERVICEEOF'
[Unit]
Description=Set wlan0 static IP for LC-Hub AP
After=network.target

[Service]
Type=oneshot
ExecStart=/sbin/ip addr add 192.168.4.1/24 dev wlan0
ExecStart=/sbin/ip link set wlan0 up
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
SERVICEEOF
systemctl daemon-reload
systemctl enable wlan0-ip.service
systemctl start wlan0-ip.service || true

echo "[4/6] Checking port 53..."
ss -tulpn | grep ':53 ' && echo "PORT 53 IN USE" || echo "PORT 53 FREE"

echo "[5/6] Stopping systemd-resolved, starting dnsmasq..."
systemctl stop systemd-resolved 2>/dev/null || true
systemctl disable systemd-resolved 2>/dev/null || true
systemctl mask systemd-resolved 2>/dev/null || true
sleep 1
systemctl start dnsmasq || echo "dnsmasq start failed, checking logs..."
journalctl -u dnsmasq -n 5 --no-pager 2>&1 | tail -5

echo "[6/6] Verification..."
echo "wlan0 IP: $(ip a show wlan0 | grep 'inet ' | awk '{print $2}')"
echo "hostapd: $(systemctl is-active hostapd)"
echo "dnsmasq: $(systemctl is-active dnsmasq)"

echo ""
echo "Done!"
