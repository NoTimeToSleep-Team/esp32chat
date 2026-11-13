#!/usr/bin/env bash
set -euo pipefail

AP_WLAN_IFACE="${AP_WLAN_IFACE:-wlan0}"
AP_UPLINK_IFACE="${AP_UPLINK_IFACE:-eth0}"
AP_COUNTRY="${AP_COUNTRY:-US}"
AP_SSID="${AP_SSID:-LocalChatPi}"
AP_PASSPHRASE="${AP_PASSPHRASE:-}"
AP_CHANNEL="${AP_CHANNEL:-6}"
AP_ADDRESS="${AP_ADDRESS:-10.42.0.1}"
AP_NETMASK="${AP_NETMASK:-255.255.255.0}"
AP_DHCP_START="${AP_DHCP_START:-10.42.0.50}"
AP_DHCP_END="${AP_DHCP_END:-10.42.0.150}"
AP_DHCP_LEASE="${AP_DHCP_LEASE:-24h}"
AP_NAT_ENABLED="${AP_NAT_ENABLED:-1}"
AP_DNS_SERVERS="${AP_DNS_SERVERS:-1.1.1.1 8.8.8.8}"
AP_DNS_WILDCARD="${AP_DNS_WILDCARD:-}"
DRY_RUN="${DRY_RUN:-0}"

DHCPCD_CONF="/etc/dhcpcd.conf"
HOSTAPD_CONF="/etc/hostapd/hostapd.conf"
HOSTAPD_DEFAULT="/etc/default/hostapd"
DNSMASQ_LOCAL_CONF="/etc/dnsmasq.d/local-chat-ap.conf"
SYSCTL_LOCAL_CONF="/etc/sysctl.d/99-local-chat-ap.conf"

log() {
    echo "[configure_pi_ap_nat] $*"
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

validate_inputs() {
    if [[ -z "${AP_PASSPHRASE}" ]]; then
        echo "AP_PASSPHRASE is required (8..63 chars)."
        exit 1
    fi
    local pass_len
    pass_len="${#AP_PASSPHRASE}"
    if (( pass_len < 8 || pass_len > 63 )); then
        echo "AP_PASSPHRASE must be 8..63 chars."
        exit 1
    fi
    if [[ "${AP_NAT_ENABLED}" != "0" && "${AP_NAT_ENABLED}" != "1" ]]; then
        echo "AP_NAT_ENABLED must be 0 or 1."
        exit 1
    fi
}

backup_file_if_exists() {
    local file_path="$1"
    if [[ -f "${file_path}" ]]; then
        local backup_path="${file_path}.bak.$(date +%Y%m%d%H%M%S)"
        run cp "${file_path}" "${backup_path}"
        log "Backup created: ${backup_path}"
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

install_packages() {
    log "Installing hostapd/dnsmasq/netfilter packages"
    run apt-get update
    run env DEBIAN_FRONTEND=noninteractive apt-get install -y hostapd dnsmasq iptables-persistent
}

configure_dhcpcd() {
    local marker="# LOCAL_CHAT_AP"
    backup_file_if_exists "${DHCPCD_CONF}"
    remove_marker_block "${marker}" "${DHCPCD_CONF}"

    local tmp_file
    tmp_file="$(mktemp)"
    cp "${DHCPCD_CONF}" "${tmp_file}"
    cat >> "${tmp_file}" <<EOF

${marker} BEGIN
interface ${AP_WLAN_IFACE}
    static ip_address=${AP_ADDRESS}/24
    nohook wpa_supplicant
${marker} END
EOF
    run cp "${tmp_file}" "${DHCPCD_CONF}"
    rm -f "${tmp_file}"
}

configure_hostapd() {
    backup_file_if_exists "${HOSTAPD_CONF}"
    backup_file_if_exists "${HOSTAPD_DEFAULT}"

    local hostapd_tmp
    hostapd_tmp="$(mktemp)"
    cat > "${hostapd_tmp}" <<EOF
country_code=${AP_COUNTRY}
interface=${AP_WLAN_IFACE}
ssid=${AP_SSID}
hw_mode=g
channel=${AP_CHANNEL}
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=${AP_PASSPHRASE}
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
EOF
    run install -m 0644 "${hostapd_tmp}" "${HOSTAPD_CONF}"
    rm -f "${hostapd_tmp}"

    local hostapd_default_tmp
    hostapd_default_tmp="$(mktemp)"
    if [[ -f "${HOSTAPD_DEFAULT}" ]]; then
        cp "${HOSTAPD_DEFAULT}" "${hostapd_default_tmp}"
    fi
    if grep -q '^DAEMON_CONF=' "${hostapd_default_tmp}" 2>/dev/null; then
        sed -i "s|^DAEMON_CONF=.*|DAEMON_CONF=\"${HOSTAPD_CONF}\"|" "${hostapd_default_tmp}"
    else
        echo "DAEMON_CONF=\"${HOSTAPD_CONF}\"" >> "${hostapd_default_tmp}"
    fi
    run install -m 0644 "${hostapd_default_tmp}" "${HOSTAPD_DEFAULT}"
    rm -f "${hostapd_default_tmp}"
}

configure_dnsmasq() {
    backup_file_if_exists "${DNSMASQ_LOCAL_CONF}"

    local dnsmasq_tmp
    dnsmasq_tmp="$(mktemp)"
    cat > "${dnsmasq_tmp}" <<EOF
interface=${AP_WLAN_IFACE}
bind-interfaces
dhcp-range=${AP_DHCP_START},${AP_DHCP_END},${AP_NETMASK},${AP_DHCP_LEASE}
dhcp-option=3,${AP_ADDRESS}
dhcp-option=6,${AP_ADDRESS}
domain-needed
bogus-priv
EOF
    if [[ -n "${AP_DNS_WILDCARD}" ]]; then
        echo "address=/#/${AP_DNS_WILDCARD}" >> "${dnsmasq_tmp}"
        echo "address=/camp.local/${AP_DNS_WILDCARD}" >> "${dnsmasq_tmp}"
        echo "address=/chat.local/${AP_DNS_WILDCARD}" >> "${dnsmasq_tmp}"
    fi
    if [[ -z "${AP_DNS_SERVERS// /}" ]]; then
        echo "no-resolv" >> "${dnsmasq_tmp}"
    else
        local dns_server
        for dns_server in ${AP_DNS_SERVERS}; do
            echo "server=${dns_server}" >> "${dnsmasq_tmp}"
        done
    fi
    run install -m 0644 "${dnsmasq_tmp}" "${DNSMASQ_LOCAL_CONF}"
    rm -f "${dnsmasq_tmp}"
}

configure_sysctl() {
    backup_file_if_exists "${SYSCTL_LOCAL_CONF}"
    local sysctl_tmp
    sysctl_tmp="$(mktemp)"
    cat > "${sysctl_tmp}" <<EOF
net.ipv4.ip_forward=1
EOF
    run install -m 0644 "${sysctl_tmp}" "${SYSCTL_LOCAL_CONF}"
    rm -f "${sysctl_tmp}"
    run sysctl --system
}

configure_iptables_nat() {
    if ! iptables -t nat -C POSTROUTING -o "${AP_UPLINK_IFACE}" -j MASQUERADE 2>/dev/null; then
        run iptables -t nat -A POSTROUTING -o "${AP_UPLINK_IFACE}" -j MASQUERADE
    fi
    if ! iptables -C FORWARD -i "${AP_UPLINK_IFACE}" -o "${AP_WLAN_IFACE}" -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null; then
        run iptables -A FORWARD -i "${AP_UPLINK_IFACE}" -o "${AP_WLAN_IFACE}" -m state --state RELATED,ESTABLISHED -j ACCEPT
    fi
    if ! iptables -C FORWARD -i "${AP_WLAN_IFACE}" -o "${AP_UPLINK_IFACE}" -j ACCEPT 2>/dev/null; then
        run iptables -A FORWARD -i "${AP_WLAN_IFACE}" -o "${AP_UPLINK_IFACE}" -j ACCEPT
    fi

    run sh -c "iptables-save > /etc/iptables/rules.v4"
}

remove_iptables_nat() {
    command -v iptables >/dev/null 2>&1 || return 0
    while iptables -t nat -C POSTROUTING -o "${AP_UPLINK_IFACE}" -j MASQUERADE 2>/dev/null; do
        run iptables -t nat -D POSTROUTING -o "${AP_UPLINK_IFACE}" -j MASQUERADE
    done
    while iptables -C FORWARD -i "${AP_UPLINK_IFACE}" -o "${AP_WLAN_IFACE}" -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null; do
        run iptables -D FORWARD -i "${AP_UPLINK_IFACE}" -o "${AP_WLAN_IFACE}" -m state --state RELATED,ESTABLISHED -j ACCEPT
    done
    while iptables -C FORWARD -i "${AP_WLAN_IFACE}" -o "${AP_UPLINK_IFACE}" -j ACCEPT 2>/dev/null; do
        run iptables -D FORWARD -i "${AP_WLAN_IFACE}" -o "${AP_UPLINK_IFACE}" -j ACCEPT
    done
    if command -v iptables-save >/dev/null 2>&1; then
        run sh -c "iptables-save > /etc/iptables/rules.v4"
    fi
}

remove_local_sysctl() {
    if [[ -f "${SYSCTL_LOCAL_CONF}" ]]; then
        run rm -f "${SYSCTL_LOCAL_CONF}"
    fi
}

restart_services() {
    run systemctl unmask hostapd
    run systemctl enable hostapd
    run systemctl restart hostapd

    run systemctl enable dnsmasq
    run systemctl restart dnsmasq

    if [[ "${AP_NAT_ENABLED}" == "1" ]]; then
        run systemctl enable netfilter-persistent
        run systemctl restart netfilter-persistent
    fi

    run systemctl restart dhcpcd
}

print_summary() {
    if [[ "${AP_NAT_ENABLED}" == "1" ]]; then
        log "AP+NAT configuration complete"
    else
        log "AP configuration complete (offline mode, NAT disabled)"
    fi
    echo ""
    echo "Quick checks:"
    echo "  ip addr show ${AP_WLAN_IFACE}"
    echo "  systemctl status hostapd --no-pager"
    echo "  systemctl status dnsmasq --no-pager"
    if [[ "${AP_NAT_ENABLED}" == "1" ]]; then
        echo "  iptables -t nat -S POSTROUTING"
    fi
    echo ""
    echo "Client network: ${AP_ADDRESS}/24"
    echo "DHCP range: ${AP_DHCP_START} - ${AP_DHCP_END}"
    if [[ -n "${AP_DNS_WILDCARD}" ]]; then
        echo "Portal DNS: camp.local, chat.local, all names -> ${AP_DNS_WILDCARD}"
    fi
}

main() {
    require_root
    validate_inputs

    if [[ "${AP_NAT_ENABLED}" == "1" ]]; then
        log "Starting AP+NAT setup wlan=${AP_WLAN_IFACE} uplink=${AP_UPLINK_IFACE} dry_run=${DRY_RUN}"
    else
        log "Starting offline AP setup wlan=${AP_WLAN_IFACE} dry_run=${DRY_RUN}"
    fi

    install_packages
    configure_dhcpcd
    configure_hostapd
    configure_dnsmasq
    if [[ "${AP_NAT_ENABLED}" == "1" ]]; then
        configure_sysctl
        configure_iptables_nat
    else
        remove_iptables_nat
        remove_local_sysctl
        run sysctl --system
    fi
    restart_services
    print_summary
}

main "$@"
