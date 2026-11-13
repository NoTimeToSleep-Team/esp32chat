#!/usr/bin/env bash
#
# Camp Edition Wi-Fi access point (offline-first, open network).
#
# This is a thin wrapper around configure_pi_ap_nat.sh with camp defaults:
#   SSID:            CAMP-CHAT
#   address:         192.168.50.1/24
#   portal:          http://192.168.50.1:18080/camp
#   Wi-Fi security:  open (no password) by default
#   NAT:             disabled by default (clients reach the camp server only)
#   DNS:             every name resolves to the camp server (captive portal)
#   Captive portal:  small HTTP server on port 80 -> /camp
#
# Run on the Raspberry Pi, from the repository root or server/ directory:
#
#   sudo bash server/scripts/configure_camp_ap.sh
#
# Optional environment:
#   CAMP_AP_ENV=/etc/camp-edition/ap.env   source a root-owned env file first
#   CAMP_AP_SSID (default CAMP-CHAT)
#   CAMP_AP_OPEN=0 (default 1; set 0 for WPA2 and CAMP_AP_PASSPHRASE)
#   CAMP_AP_WLAN_IFACE (default wlan0)
#   CAMP_AP_COUNTRY (default RU), CAMP_AP_CHANNEL (default 6)
#   CAMP_AP_ADDRESS (default 192.168.50.1)
#   CAMP_AP_DHCP_START / CAMP_AP_DHCP_END
#   CAMP_PORTAL_PORT (default 18080)
#   CAMP_PORTAL_URL (default http://<address>:<port>/camp)
#   CAMP_CAPTIVE_PORTAL=0 (default 1)
#   CAMP_CAPTIVE_PORTAL_PORT (default 80)
#   CAMP_AP_NAT_ENABLED=1 (default 0, requires an uplink)
#   CAMP_AP_UPLINK_IFACE (default eth0, only used with NAT)
#   CAMP_AP_DNS_SERVERS (default empty offline, external DNS with NAT)
#   CAMP_AP_DNS_WILDCARD (default address offline, empty with NAT)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -n "${CAMP_AP_ENV:-}" ]]; then
    if [[ ! -r "${CAMP_AP_ENV}" ]]; then
        echo "CAMP_AP_ENV is not readable: ${CAMP_AP_ENV}" >&2
        exit 1
    fi
    # shellcheck disable=SC1090
    source "${CAMP_AP_ENV}"
fi

CAMP_AP_SSID="${CAMP_AP_SSID:-CAMP-CHAT}"
CAMP_AP_OPEN="${CAMP_AP_OPEN:-1}"
CAMP_AP_PASSPHRASE="${CAMP_AP_PASSPHRASE:-}"
CAMP_AP_WLAN_IFACE="${CAMP_AP_WLAN_IFACE:-wlan0}"
CAMP_AP_COUNTRY="${CAMP_AP_COUNTRY:-RU}"
CAMP_AP_CHANNEL="${CAMP_AP_CHANNEL:-6}"
CAMP_AP_ADDRESS="${CAMP_AP_ADDRESS:-192.168.50.1}"
CAMP_AP_DHCP_START="${CAMP_AP_DHCP_START:-192.168.50.50}"
CAMP_AP_DHCP_END="${CAMP_AP_DHCP_END:-192.168.50.150}"
CAMP_PORTAL_PORT="${CAMP_PORTAL_PORT:-18080}"
CAMP_PORTAL_URL="${CAMP_PORTAL_URL:-http://${CAMP_AP_ADDRESS}:${CAMP_PORTAL_PORT}/camp}"
CAMP_AP_NAT_ENABLED="${CAMP_AP_NAT_ENABLED:-0}"
CAMP_AP_UPLINK_IFACE="${CAMP_AP_UPLINK_IFACE:-eth0}"
CAMP_CAPTIVE_PORTAL="${CAMP_CAPTIVE_PORTAL:-1}"
CAMP_CAPTIVE_PORTAL_PORT="${CAMP_CAPTIVE_PORTAL_PORT:-80}"

if [[ -z "${CAMP_AP_DNS_SERVERS+x}" ]]; then
    if [[ "${CAMP_AP_NAT_ENABLED}" == "1" ]]; then
        CAMP_AP_DNS_SERVERS="1.1.1.1 8.8.8.8"
    else
        CAMP_AP_DNS_SERVERS=""
    fi
fi
if [[ -z "${CAMP_AP_DNS_WILDCARD+x}" ]]; then
    if [[ "${CAMP_AP_NAT_ENABLED}" == "1" ]]; then
        CAMP_AP_DNS_WILDCARD=""
    else
        CAMP_AP_DNS_WILDCARD="${CAMP_AP_ADDRESS}"
    fi
fi

for value in \
    "${CAMP_AP_SSID}" "${CAMP_AP_PASSPHRASE}" "${CAMP_AP_COUNTRY}" \
    "${CAMP_AP_CHANNEL}" "${CAMP_AP_ADDRESS}" "${CAMP_PORTAL_URL}" \
    "${CAMP_AP_DNS_SERVERS}" "${CAMP_AP_DNS_WILDCARD}"; do
    if [[ "${value}" == *$'\n'* || "${value}" == *$'\r'* ]]; then
        echo "Camp AP settings must not contain newlines." >&2
        exit 1
    fi
done
if [[ "${CAMP_PORTAL_URL}" != http://* && "${CAMP_PORTAL_URL}" != https://* ]]; then
    echo "CAMP_PORTAL_URL must start with http:// or https://." >&2
    exit 1
fi
if [[ "${CAMP_PORTAL_URL}" == *'"'* || "${CAMP_PORTAL_URL}" == *" "* ]]; then
    echo "CAMP_PORTAL_URL must not contain spaces or quotes." >&2
    exit 1
fi
if [[ "${CAMP_AP_OPEN}" != "0" && "${CAMP_AP_OPEN}" != "1" ]]; then
    echo "CAMP_AP_OPEN must be 0 or 1." >&2
    exit 1
fi
if [[ "${CAMP_AP_OPEN}" != "1" && -z "${CAMP_AP_PASSPHRASE}" ]]; then
    echo "Set CAMP_AP_PASSPHRASE (8..63 chars) when CAMP_AP_OPEN=0." >&2
    exit 1
fi
if [[ "${CAMP_CAPTIVE_PORTAL}" != "0" && "${CAMP_CAPTIVE_PORTAL}" != "1" ]]; then
    echo "CAMP_CAPTIVE_PORTAL must be 0 or 1." >&2
    exit 1
fi
if [[ ! "${CAMP_CAPTIVE_PORTAL_PORT}" =~ ^[0-9]+$ ]] || (( CAMP_CAPTIVE_PORTAL_PORT < 1 || CAMP_CAPTIVE_PORTAL_PORT > 65535 )); then
    echo "CAMP_CAPTIVE_PORTAL_PORT must be a TCP port number." >&2
    exit 1
fi

export AP_SSID="${CAMP_AP_SSID}"
export AP_OPEN="${CAMP_AP_OPEN}"
export AP_PASSPHRASE="${CAMP_AP_PASSPHRASE}"
export AP_WLAN_IFACE="${CAMP_AP_WLAN_IFACE}"
export AP_COUNTRY="${CAMP_AP_COUNTRY}"
export AP_CHANNEL="${CAMP_AP_CHANNEL}"
export AP_ADDRESS="${CAMP_AP_ADDRESS}"
export AP_DHCP_START="${CAMP_AP_DHCP_START}"
export AP_DHCP_END="${CAMP_AP_DHCP_END}"
export AP_NAT_ENABLED="${CAMP_AP_NAT_ENABLED}"
export AP_UPLINK_IFACE="${CAMP_AP_UPLINK_IFACE}"
export AP_DNS_SERVERS="${CAMP_AP_DNS_SERVERS}"
export AP_DNS_WILDCARD="${CAMP_AP_DNS_WILDCARD}"

echo "[configure_camp_ap] SSID=${CAMP_AP_SSID} open=${CAMP_AP_OPEN} address=${CAMP_AP_ADDRESS} portal=${CAMP_PORTAL_URL} nat=${CAMP_AP_NAT_ENABLED}"

bash "${HERE}/configure_pi_ap_nat.sh"

install_captive_portal() {
    if [[ "${CAMP_CAPTIVE_PORTAL}" != "1" ]]; then
        echo "[configure_camp_ap] captive portal disabled"
        return 0
    fi
    local script="${HERE}/camp_captive_portal.py"
    if [[ ! -f "${script}" ]]; then
        echo "[configure_camp_ap] missing ${script}" >&2
        return 1
    fi
    if [[ "${DRY_RUN:-0}" == "1" ]]; then
        echo "[configure_camp_ap] DRY-RUN: would install camp-captive-portal.service"
        echo "[configure_camp_ap] DRY-RUN: target=${CAMP_PORTAL_URL} port=${CAMP_CAPTIVE_PORTAL_PORT}"
        return 0
    fi

    local unit="/etc/systemd/system/camp-captive-portal.service"
    cat > "${unit}" <<EOF
[Unit]
Description=Camp Edition captive portal (open Wi-Fi)
After=network-online.target hostapd.service dnsmasq.service
Wants=hostapd.service dnsmasq.service

[Service]
Type=simple
User=nobody
Group=nogroup
ExecStart=/usr/bin/python3 "${script}" --listen 0.0.0.0 --port ${CAMP_CAPTIVE_PORTAL_PORT} --target "${CAMP_PORTAL_URL}"
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
RestrictAddressFamilies=AF_INET AF_INET6
Restart=always
RestartSec=3
MemoryMax=64M

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable camp-captive-portal >/dev/null 2>&1 || true
    systemctl restart camp-captive-portal
    echo "[configure_camp_ap] captive portal: http://${CAMP_AP_ADDRESS}:${CAMP_CAPTIVE_PORTAL_PORT}/ -> ${CAMP_PORTAL_URL}"
}

install_captive_portal
