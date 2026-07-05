#!/usr/bin/env bash
set -euo pipefail

AP_WLAN_IFACE="${AP_WLAN_IFACE:-wlan0}"
AP_UPLINK_IFACE="${AP_UPLINK_IFACE:-eth0}"
DRY_RUN="${DRY_RUN:-0}"

DHCPCD_CONF="/etc/dhcpcd.conf"
DNSMASQ_LOCAL_CONF="/etc/dnsmasq.d/local-chat-ap.conf"
SYSCTL_LOCAL_CONF="/etc/sysctl.d/99-local-chat-ap.conf"

log() {
    echo "[disable_pi_ap_nat] $*"
}

run() {
    if [[ "${DRY_RUN}" == "1" ]]; then
        log "DRY-RUN: $*"
        return 0
    fi
    "$@"
}

require_root() {
    if [[ "${EUID}" -ne 0 ]]; then
        echo "Run as root: sudo bash $0"
        exit 1
    fi
}

remove_marker_block() {
    local marker="$1"
    local file_path="$2"
    if [[ ! -f "${file_path}" ]]; then
        return 0
    fi

    local tmp_file
    tmp_file="$(mktemp)"
    awk -v marker="${marker}" '
        $0 == marker " BEGIN" {skip=1; next}
        $0 == marker " END" {skip=0; next}
        skip != 1 {print}
    ' "${file_path}" > "${tmp_file}"
    run cp "${tmp_file}" "${file_path}"
    rm -f "${tmp_file}"
}

remove_firewall_rules() {
    while iptables -t nat -C POSTROUTING -o "${AP_UPLINK_IFACE}" -j MASQUERADE 2>/dev/null; do
        run iptables -t nat -D POSTROUTING -o "${AP_UPLINK_IFACE}" -j MASQUERADE
    done

    while iptables -C FORWARD -i "${AP_UPLINK_IFACE}" -o "${AP_WLAN_IFACE}" -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null; do
        run iptables -D FORWARD -i "${AP_UPLINK_IFACE}" -o "${AP_WLAN_IFACE}" -m state --state RELATED,ESTABLISHED -j ACCEPT
    done

    while iptables -C FORWARD -i "${AP_WLAN_IFACE}" -o "${AP_UPLINK_IFACE}" -j ACCEPT 2>/dev/null; do
        run iptables -D FORWARD -i "${AP_WLAN_IFACE}" -o "${AP_UPLINK_IFACE}" -j ACCEPT
    done

    run sh -c "iptables-save > /etc/iptables/rules.v4"
}

main() {
    require_root
    log "Disabling AP+NAT setup wlan=${AP_WLAN_IFACE} uplink=${AP_UPLINK_IFACE} dry_run=${DRY_RUN}"

    remove_marker_block "# LOCAL_CHAT_AP" "${DHCPCD_CONF}"

    if [[ -f "${DNSMASQ_LOCAL_CONF}" ]]; then
        run rm -f "${DNSMASQ_LOCAL_CONF}"
    fi

    if [[ -f "${SYSCTL_LOCAL_CONF}" ]]; then
        run rm -f "${SYSCTL_LOCAL_CONF}"
    fi

    remove_firewall_rules

    run systemctl restart dhcpcd
    run systemctl restart dnsmasq
    run systemctl stop hostapd

    run sysctl --system

    log "Done. hostapd stopped, local dnsmasq AP file removed, NAT rules removed."
}

main "$@"
