#!/usr/bin/env bash
# lc — Local Chat Server management commands (v0.1).
# Installed as a symlink to /usr/local/bin/lc (see install_pi.sh).
#
#   lc status     — service + health check
#   lc setup      — re-run the setup wizard (sudo)
#   lc start      — start the server now (sudo)
#   lc stop       — stop the server (sudo)
#   lc update     — update from a new release tarball (data/ and app.env are kept)
#   lc backup     — archive data/ and app.env
#   lc logs       — install log + service journal
#   lc uninstall  — stop and remove (data kept; --purge removes everything)
#   lc version    — server version
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/local-chat-server}"
SERVICE_NAME="local-chat-server"
ENV_FILE="${APP_ROOT}/config/app.env"
INSTALL_LOG="/var/log/lc-install.log"

require_root() {
    if [[ "${EUID}" -ne 0 ]]; then
        echo "Root required: sudo lc $1" >&2
        exit 1
    fi
}

port() {
    local p
    p="$(sed -n 's/^LCS_PORT=//p' "${ENV_FILE}" 2>/dev/null | tail -1)"
    echo "${p:-18080}"
}

systemd_ok() {
    command -v systemctl >/dev/null 2>&1 && [[ -d /run/systemd/system ]]
}

cmd_status() {
    echo "Local Chat Server"
    echo "  version: $(cmd_version)"
    if systemd_ok; then
        echo "  service: $(systemctl is-active ${SERVICE_NAME})"
    else
        echo "  service: systemd not available"
    fi
    echo "  port:    $(port)"
    if curl -fsS "http://127.0.0.1:$(port)/health" >/dev/null 2>&1; then
        echo "  health:  ok (http://127.0.0.1:$(port)/health)"
    else
        echo "  health:  NOT RESPONDING"
    fi
}

cmd_setup() {
    require_root setup
    if [[ ! -f "${APP_ROOT}/setup/wizard.sh" ]]; then
        echo "Wizard not found: ${APP_ROOT}/setup/wizard.sh" >&2
        exit 1
    fi
    exec bash "${APP_ROOT}/setup/wizard.sh" "$@"
}

cmd_start() {
    require_root start
    if ! systemd_ok; then
        echo "systemd is not available on this system" >&2
        exit 1
    fi
    systemctl start "${SERVICE_NAME}"
    echo "Server started (port $(port))"
}

cmd_stop() {
    require_root stop
    if ! systemd_ok; then
        echo "systemd is not available on this system" >&2
        exit 1
    fi
    systemctl stop "${SERVICE_NAME}"
    echo "Server stopped"
}

cmd_version() {
    sed -n 's/^__version__ = "\([^"]*\)"/\1/p' "${APP_ROOT}/app/version.py" 2>/dev/null | head -1
}

cmd_update() {
    require_root update
    # shellcheck disable=SC1091
    . "${APP_ROOT}/setup/lib.sh"

    LC_WORK="$(mktemp -d)"
    trap '[[ -n "${LC_WORK:-}" ]] && rm -rf "${LC_WORK}"' EXIT
    lc_log "downloading the new release…"
    LC_PKG_ROOT="$(lc_fetch_release "${LC_WORK}")"

    lc_log "updating the code (data/ and app.env are preserved)"
    SOURCE_ROOT="${LC_PKG_ROOT}/server" \
        bash "${LC_PKG_ROOT}/server/scripts/install_pi.sh" --no-setup
    lc_log "update complete: $(cmd_version)"
}

cmd_backup() {
    require_root backup
    local stamp out
    stamp="$(date +%Y%m%d-%H%M%S)"
    mkdir -p "${APP_ROOT}/data/backups"
    out="${APP_ROOT}/data/backups/lc-backup-${stamp}.tar.gz"
    tar -czf "${out}" -C "${APP_ROOT}" data config/app.env 2>/dev/null \
        || tar -czf "${out}" -C "${APP_ROOT}" data
    chmod 600 "${out}"
    echo "Backup created: ${out}"
}

cmd_logs() {
    echo "=== install log (${INSTALL_LOG}) ==="
    if [[ -f "${INSTALL_LOG}" ]]; then
        tail -n 80 "${INSTALL_LOG}"
    else
        echo "(empty)"
    fi
    echo ""
    echo "=== service ${SERVICE_NAME} (last 100 lines) ==="
    if systemd_ok; then
        journalctl -u "${SERVICE_NAME}" -n 100 --no-pager 2>/dev/null || true
    else
        tail -n 100 "${APP_ROOT}/data/logs/smoke-server.log" 2>/dev/null || echo "(no log)"
    fi
}

cmd_uninstall() {
    require_root uninstall
    local purge=0
    [[ "${1:-}" == "--purge" ]] && purge=1

    echo "Removing Local Chat Server from ${APP_ROOT}"
    if [[ "${purge}" != "1" ]]; then
        echo "Data (${APP_ROOT}/data) will be kept."
    fi
    read -r -p "Are you sure? Type yes: " answer
    [[ "${answer}" == "yes" ]] || { echo "Cancelled"; exit 0; }

    if systemd_ok; then
        systemctl stop "${SERVICE_NAME}" 2>/dev/null || true
        systemctl disable "${SERVICE_NAME}" 2>/dev/null || true
    fi
    rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
    systemctl daemon-reload 2>/dev/null || true
    rm -f /usr/local/bin/lc

    if [[ "${purge}" == "1" ]]; then
        rm -rf "${APP_ROOT}"
        echo "Removed completely (data included)."
    else
        mv "${APP_ROOT}" "${APP_ROOT}.removed-$(date +%Y%m%d-%H%M%S)"
        echo "Code removed; data kept in ${APP_ROOT}.removed-*"
    fi
}

usage() {
    cat <<EOF
lc — Local Chat Server management
  lc status            service and portal status
  lc setup             setup wizard (sudo lc setup)
  lc start             start the server now (sudo)
  lc stop              stop the server (sudo)
  lc update            update to a new release (sudo)
  lc backup            back up data and settings (sudo)
  lc logs              logs
  lc uninstall         remove (sudo; data is kept)
  lc uninstall --purge remove completely, data included (sudo)
  lc version           server version
EOF
}

case "${1:-}" in
    status) cmd_status ;;
    setup) shift; cmd_setup "$@" ;;
    start) cmd_start ;;
    stop) cmd_stop ;;
    update) cmd_update ;;
    backup) cmd_backup ;;
    logs) cmd_logs ;;
    uninstall) cmd_uninstall "${2:-}" ;;
    version) cmd_version ;;
    -h|--help|help|"") usage ;;
    *) echo "unknown command: ${1:-}" >&2; usage; exit 2 ;;
esac
