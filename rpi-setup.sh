#!/bin/bash
# RPi 5 AP setup: LC-Hub open network + captive portal
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}[1/6] Installing packages...${NC}"
sudo apt update
sudo apt install -y hostapd dnsmasq python3-pip iptables-persistent

echo -e "${GREEN}[2/6] Configuring hostapd...${NC}"
# Backup existing config if any
if [ -f /etc/hostapd/hostapd.conf ]; then
    sudo cp /etc/hostapd/hostapd.conf /etc/hostapd/hostapd.conf.backup 2>/dev/null || true
fi

sudo tee /etc/hostapd/hostapd.conf > /dev/null << 'EOF'
interface=wlan0
driver=nl80211
ssid=LC-Hub
hw_mode=g
channel=6
auth_algs=1
wmm_enabled=0
EOF

sudo systemctl unmask hostapd 2>/dev/null || true
sudo systemctl enable hostapd

echo -e "${GREEN}[3/6] Configuring dnsmasq...${NC}"
sudo mv /etc/dnsmasq.conf /etc/dnsmasq.conf.backup 2>/dev/null || true
sudo tee /etc/dnsmasq.conf > /dev/null << 'EOF'
interface=wlan0
dhcp-range=192.168.4.2,192.168.4.50,255.255.255.0,24h
dhcp-option=3,192.168.4.1
dhcp-option=6,192.168.4.1
address=/#/192.168.4.1
server=8.8.8.8
no-hosts
EOF

sudo systemctl enable dnsmasq

echo -e "${GREEN}[4/6] Setting static IP for wlan0...${NC}"
if ! grep -q 'interface wlan0' /etc/dhcpcd.conf; then
    echo -e '\ninterface wlan0\nstatic ip_address=192.168.4.1/24\nnohook wpa_supplicant' | sudo tee -a /etc/dhcpcd.conf
fi

echo -e "${GREEN}[5/6] Adding captive portal redirect (port 80 -> 18080)...${NC}"
sudo iptables -C PREROUTING -t nat -i wlan0 -p tcp --dport 80 -j REDIRECT --to-port 18080 2>/dev/null || \
    sudo iptables -t nat -A PREROUTING -i wlan0 -p tcp --dport 80 -j REDIRECT --to-port 18080
sudo netfilter-persistent save

echo -e "${GREEN}[6/6] Done!${NC}"
echo -e "${YELLOW}--- Summary ---${NC}"
echo "Wi-Fi SSID: LC-Hub (open, no password)"
echo "Server IP:   192.168.4.1"
echo "DHCP range: 192.168.4.2 - 192.168.4.50"
echo "Captive:    ANY domain -> 192.168.4.1:18080"
echo ""
echo "Next steps:"
echo "1. sudo reboot"
echo "2. After reboot, connect to LC-Hub Wi-Fi"
echo "3. Copy server files to ~/lc-server"
echo "4. Run rpi-deploy-server.sh"
