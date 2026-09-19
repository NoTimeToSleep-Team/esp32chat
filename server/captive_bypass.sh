#!/bin/bash
# Captive Portal Bypass — helps pass WiFi login pages
# Usage: captive_bypass.sh <SSID> <password>

SSID=""
WIFI_PASS=""

if [ -z "" ]; then
  echo "Usage: captive_bypass.sh <SSID> [WiFi_password]"
  exit 1
fi

echo "=== Подключаюсь к  ==="
# Stop AP
sudo systemctl stop hostapd
sudo ip link set wlan0 down
sudo iw dev wlan0 set type managed
sudo ip link set wlan0 up

# Connect
if [ -n "" ]; then
  wpa_passphrase "" "" | sudo tee /etc/wpa_supplicant/wpa_temp.conf > /dev/null
  sudo wpa_supplicant -B -i wlan0 -c /etc/wpa_supplicant/wpa_temp.conf
else
  sudo iw dev wlan0 connect ""
fi

sleep 5

# Get IP
sudo dhclient wlan0 2>/dev/null || true
IP=$(ip addr show wlan0 | grep 'inet ' | awk '{print $2}' | cut -d/ -f1)
echo "IP: $IP"

# Check for captive portal
echo "=== Проверяю captive portal ==="
HTTP=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://example.com 2>/dev/null)
echo "HTTP status: $HTTP"

if [ "$HTTP" = "302" ] || [ "$HTTP" = "301" ] || [ "$HTTP" = "200" ]; then
  REDIR=$(curl -s -o /dev/null -w '%{redirect_url}' --max-time 5 http://example.com 2>/dev/null)
  echo "Redirect to: $REDIR"
  if [ -n "$REDIR" ]; then
    # Fetch the captive portal page and save it
    curl -s --max-time 5 "$REDIR" -o /tmp/captive_page.html 2>/dev/null
    echo "Captive portal detected. Login page saved to /tmp/captive_page.html"
    echo "Access via: http://$IP:18080/static/captive_login.html"
  fi
fi

echo "Done. IP: $IP"
