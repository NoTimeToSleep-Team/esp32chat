#!/usr/bin/env bash
# Local-only infrastructure operator.
#
# This is the ONLY supported path for host/network service operations.  It is
# deliberately a root TTY tool: the web application and its chat administrators
# have no route, credential or capability to reach it.
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "lc-operator: run as root on the device console or over SSH" >&2
    exit 1
fi

if [ ! -t 0 ]; then
    echo "lc-operator: an interactive TTY is required" >&2
    exit 1
fi

usage() {
    cat <<'EOF'
Usage: sudo lc-operator <command> [options]

  status
  restart-service <local-chat-server|local-chat-proxy|hostapd|dnsmasq>
  reboot --confirm
  shutdown --confirm

Host actions are intentionally unavailable from the web admin panel.
EOF
}

case "${1:-}" in
    status)
        systemctl --no-pager --full status local-chat-server local-chat-proxy hostapd dnsmasq 2>/dev/null || true
        ;;
    restart-service)
        service="${2:-}"
        case "$service" in
            local-chat-server|local-chat-proxy|hostapd|dnsmasq) ;;
            *) echo "lc-operator: service not allowed: ${service:-<empty>}" >&2; exit 2 ;;
        esac
        systemctl restart "$service"
        systemctl is-active "$service"
        ;;
    reboot)
        [ "${2:-}" = "--confirm" ] || { echo "lc-operator: reboot requires --confirm" >&2; exit 2; }
        systemctl reboot
        ;;
    shutdown)
        [ "${2:-}" = "--confirm" ] || { echo "lc-operator: shutdown requires --confirm" >&2; exit 2; }
        systemctl poweroff
        ;;
    *)
        usage
        exit 2
        ;;
esac
