#!/usr/bin/env bash
#
# Camp Edition Wi-Fi access point (offline-first).
#
# This is a thin wrapper around configure_pi_ap_nat.sh with camp defaults:
#   SSID:      CAMP-CHAT
#   address:   192.168.50.1/24
#   portal:    http://192.168.50.1:18080/camp
#   NAT:       disabled by default (clients reach the camp server only)
#   DNS:       every name resolves to the camp server (captive portal)
#
# Run on the Raspberry Pi, from the repository root or server/ directory:
#
#   sudo CAMP_AP_PASSPHRASE='replace-with-strong-pass' \
#        bash server/scripts/configure_camp_ap.sh
#
# Optional environment:
#   CAMP_AP_ENV=/etc/camp-edition/ap.env   source a root-owned env file first
#   CAMP_AP_SSID / CAMP_AP_PASSPHRASE
#   CAMP_AP_WLAN_IFACE (default wlan0)
#   CAMP_AP_COUNTRY (default RU), CAMP_AP_CHANNEL (default 6)
#   CAMP_AP_ADDRESS (default 192.168.50.1)
#   CAMP_AP_DHCP_START / CAMP_AP_DHCP_END
#   CAMP_PORTAL_PORT (default 18080, used in the printed portal URL)
#   CAMP_AP_NAT_ENABLED=1 (default 0, requires an uplink)
#   CAMP_AP_UPLINK_IFACE (default eth0, only used with NAT)
#   CAMP_AP_DNS_SERVERS (default empty in camp mode, e.g. "1.1.1.1 8.8.8.8")
#   CAMP_AP_DNS_WILDCARD (default CAMP_AP_ADDRESS; set empty to disable)
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
CAMP_AP_PASSPHRASE="${CAMP_AP_PASSPHRASE:-}"
CAMP_AP_WLAN_IFACE="${CAMP_AP_WLAN_IFACE:-wlan0}"
CAMP_AP_COUNTRY="${CAMP_AP_COUNTRY:-RU}"
CAMP_AP_CHANNEL="${CAMP_AP_CHANNEL:-6}"
CAMP_AP_ADDRESS="${CAMP_AP_ADDRESS:-192.168.50.1}"
CAMP_AP_DHCP_START="${CAMP_AP_DHCP_START:-192.168.50.50}"
CAMP_AP_DHCP_END="${CAMP_AP_DHCP_END:-192.168.50.150}"
CAMP_PORTAL_PORT="${CAMP_PORTAL_PORT:-18080}"
CAMP_AP_NAT_ENABLED="${CAMP_AP_NAT_ENABLED:-0}"
CAMP_AP_UPLINK_IFACE="${CAMP_AP_UPLINK_IFACE:-eth0}"
CAMP_AP_DNS_SERVERS="${CAMP_AP_DNS_SERVERS:-}"
CAMP_AP_DNS_WILDCARD="${CAMP_AP_DNS_WILDCARD-${CAMP_AP_ADDRESS}}"

if [[ -z "${CAMP_AP_PASSPHRASE}" ]]; then
    echo "Set CAMP_AP_PASSPHRASE (8..63 chars)." >&2
    exit 1
fi

export AP_SSID="${CAMP_AP_SSID}"
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

echo "[configure_camp_ap] SSID=${CAMP_AP_SSID} address=${CAMP_AP_ADDRESS} portal=http://${CAMP_AP_ADDRESS}:${CAMP_PORTAL_PORT}/camp nat=${CAMP_AP_NAT_ENABLED}"
exec bash "${HERE}/configure_pi_ap_nat.sh"
