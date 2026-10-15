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
#   lc export     — bundle data/ + app.env for moving to another server
#   lc import     — restore an export on this server (safety backup first)
#   lc logs       — install log + service journal
#   lc uninstall  — stop and remove (data kept; --purge removes everything)
#   lc version    — server version
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/local-chat-server}"
SERVICE_NAME="local-chat-server"
APP_USER="${APP_USER:-localchat}"
APP_GROUP="${APP_GROUP:-localchat}"
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
    p="$(sed -n 's/^LCS_PORT=//p' "${ENV_FILE}" 2>/dev/null | tail -1 || true)"
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
    sed -n 's/^__version__ = "\([^"]*\)"/\1/p' "${APP_ROOT}/app/version.py" 2>/dev/null | head -1 || true
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

# True when the server holds real data (users or chat messages).
data_present() {
    local db="${APP_ROOT}/data/sqlite/local_chat.db"
    [[ -f "${db}" ]] || return 1
    python3 - "${db}" <<'PY' 2>/dev/null
import sqlite3, sys
try:
    c = sqlite3.connect(sys.argv[1])
    users = c.execute("select count(*) from users").fetchone()[0]
    try:
        messages = c.execute("select count(*) from chat_messages").fetchone()[0]
    except Exception:
        messages = 0
    sys.exit(0 if (users or messages) else 1)
except Exception:
    sys.exit(1)
PY
}

# Builds an export archive (data + config/app.env + EXPORT_INFO) with a .sha256.
# Call it with the service stopped for a consistent sqlite snapshot.
make_export_archive() {
    local out="$1" info_dir
    info_dir="$(mktemp -d)"
    {
        echo "Local Chat Server export"
        echo "version: $(cmd_version)"
        echo "date: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
        echo "host: $(hostname)"
    } > "${info_dir}/EXPORT_INFO.txt"
    mkdir -p "$(dirname "${out}")"
    if ! tar -czf "${out}" -C "${APP_ROOT}" \
        --exclude='data/backups' --exclude='data/logs' --exclude='data/incidents' \
        data config/app.env \
        -C "${info_dir}" EXPORT_INFO.txt; then
        rm -rf "${info_dir}"
        rm -f "${out}"
        return 1
    fi
    rm -rf "${info_dir}"
    ( cd "$(dirname "${out}")" && sha256sum "$(basename "${out}")" ) > "${out}.sha256"
    chmod 600 "${out}" "${out}.sha256" 2>/dev/null || true
    return 0
}

cmd_export() {
    require_root export
    local stamp out stopped=0 ok=1
    stamp="$(date +%Y%m%d-%H%M%S)"
    out="${1:-${APP_ROOT}/data/backups/lc-export-${stamp}.tar.gz}"

    # A consistent sqlite snapshot: stop the server while the archive is built.
    if systemd_ok && systemctl is-active --quiet "${SERVICE_NAME}"; then
        echo "Stopping the server for a consistent snapshot…"
        if systemctl stop "${SERVICE_NAME}"; then stopped=1; fi
    fi
    make_export_archive "${out}" || ok=0
    if [[ "${stopped}" == "1" ]]; then
        systemctl start "${SERVICE_NAME}" 2>/dev/null || true
    fi
    if [[ "${ok}" != "1" ]]; then
        echo "Export failed" >&2
        exit 1
    fi
    echo "Export created: ${out}"
    echo "  size:   $(du -h "${out}" | cut -f1)"
    echo "  sha256: $(cut -d' ' -f1 "${out}.sha256")"
    echo "Copy the file (and its .sha256) to the other server and run there:"
    echo "  sudo lc import $(basename "${out}")"
}

cmd_import() {
    require_root import
    local src="" assume_yes=0 arg listing info_ver newer="" pre stopped=0 tmp ok=1
    for arg in "$@"; do
        case "${arg}" in
            --yes) assume_yes=1 ;;
            *) src="${arg}" ;;
        esac
    done
    [[ -n "${src}" ]] || { echo "usage: sudo lc import <export-file.tar.gz> [--yes]" >&2; exit 2; }
    [[ -f "${src}" ]] || { echo "not found: ${src}" >&2; exit 2; }

    if [[ -f "${src}.sha256" ]]; then
        ( cd "$(dirname "${src}")" && sha256sum -c "$(basename "${src}").sha256" ) >&2 \
            || { echo "checksum mismatch — refusing to import" >&2; exit 1; }
    fi
    listing="$(tar -tzf "${src}" 2>/dev/null || true)"
    if ! grep -q '^data/sqlite/' <<< "${listing}"; then
        echo "this file does not look like an LC export (no data/sqlite inside)" >&2
        exit 1
    fi

    info_ver="$(tar -xzOf "${src}" EXPORT_INFO.txt 2>/dev/null | sed -n 's/^version: //p' | head -1 || true)"
    if [[ -n "${info_ver}" && "${info_ver}" != "$(cmd_version)" ]]; then
        newer="$(printf '%s\n%s\n' "${info_ver}" "$(cmd_version)" | sort -V | tail -1)"
        if [[ "${newer}" == "${info_ver}" ]]; then
            echo "WARNING: the export is from a newer version (${info_ver} vs $(cmd_version))." >&2
            echo "         Run 'sudo lc update' first if the import misbehaves." >&2
        fi
    fi

    echo "Import: ${src}"
    [[ -n "${info_ver}" ]] && echo "  exported from version: ${info_ver}"
    echo "  local version:         $(cmd_version)"
    echo "The current data will be REPLACED (an export of it is saved to /var/backups first, when it is not empty)."
    if [[ "${assume_yes}" != "1" ]]; then
        read -r -p "Type yes to continue: " answer
        [[ "${answer}" == "yes" ]] || { echo "Cancelled"; exit 0; }
    fi

    # Stop first: the pre-import export must be a consistent snapshot.
    if systemd_ok && systemctl is-active --quiet "${SERVICE_NAME}"; then
        if systemctl stop "${SERVICE_NAME}"; then stopped=1; fi
    fi

    pre=""
    if data_present; then
        pre="/var/backups/lc-pre-import-$(date +%Y%m%d-%H%M%S).tar.gz"
        mkdir -p /var/backups
        if ! make_export_archive "${pre}"; then
            echo "ERROR: the pre-import backup could not be created — refusing to import." >&2
            if [[ "${stopped}" == "1" ]]; then systemctl start "${SERVICE_NAME}" 2>/dev/null || true; fi
            exit 1
        fi
        echo "Pre-import export: ${pre}"
        echo "  to roll back:   sudo lc import ${pre} --yes"
    else
        echo "No existing data — skipping the pre-import export."
    fi

    tmp="$(mktemp -d)"
    if ! tar -xzf "${src}" -C "${tmp}"; then
        ok=0
    elif [[ ! -d "${tmp}/data" ]]; then
        ok=0
    else
        rm -rf "${APP_ROOT}/data"
        mv "${tmp}/data" "${APP_ROOT}/data"
        if [[ -f "${tmp}/config/app.env" ]]; then
            install -m 0600 -o root -g root "${tmp}/config/app.env" "${APP_ROOT}/config/app.env"
        fi
        chown -R "${APP_USER}:${APP_GROUP}" "${APP_ROOT}/data" 2>/dev/null || true
    fi
    rm -rf "${tmp}"

    if [[ "${stopped}" == "1" || "${ok}" == "1" ]]; then
        systemctl start "${SERVICE_NAME}" 2>/dev/null || true
    fi
    if [[ "${ok}" != "1" ]]; then
        echo "Import failed — the old data is intact (see the safety backup)." >&2
        exit 1
    fi

    local i
    for i in $(seq 1 30); do
        if curl -fsS "http://127.0.0.1:$(port)/health" >/dev/null 2>&1; then break; fi
        sleep 2
    done
    if curl -fsS "http://127.0.0.1:$(port)/health" >/dev/null 2>&1; then
        echo "Import finished — the server is up: http://127.0.0.1:$(port)/"
    else
        echo "Import finished, but /health is not answering yet — check: lc logs" >&2
    fi
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
    cat <<'EOF'
lc — Local Chat Server management (v0.1)

Usage:
  lc <command> [arguments]

Commands:
  status                  Show the server state: version, service, port, /health.
  version                 Print the installed server version.
  start                   Start the server service now. (sudo)
  stop                    Stop the server service now. (sudo)
  setup [--preseed FILE]  Run the setup wizard: administrator, Wi-Fi AP, port,
                          registration mode, autostart. (sudo)
                            --preseed FILE  read the answers from a KEY=VALUE
                                            file instead of asking questions
  update                  Download and install the newest release from GitHub;
                          data/ and config/app.env are kept. (sudo)
  backup                  Archive data/ and config/app.env into
                          data/backups/lc-backup-<timestamp>.tar.gz. (sudo)
  export [FILE]           Bundle data/ + config/app.env for moving to another
                          server (default: data/backups/lc-export-<stamp>.tar.gz;
                          a .sha256 is written next to the archive). (sudo)
  import FILE [--yes]     Replace this server's data with an export file
                          (checks the .sha256 if present; exports the current
                          data to /var/backups first when it is not empty). (sudo)
  logs                    Show the install log and the last 100 service log lines.
  uninstall               Stop and remove the server code; data is kept. (sudo)
  uninstall --purge       Also delete data and settings — irreversible. (sudo)
  help                    Show this help (same as -h / --help).

Examples:
  sudo lc update          update from the newest GitHub release
  sudo lc setup           change the Wi-Fi AP, admin password, registration mode
  lc status               quick check that the server is alive
  sudo lc export /tmp/lc-export.tar.gz   bundle the data for another server
  sudo lc import /tmp/lc-export.tar.gz   restore that data on this server
  sudo lc uninstall --purge   remove the server completely, data included

Documentation: docs/INSTALL.md in the release archive.
EOF
}

case "${1:-}" in
    status) cmd_status ;;
    setup) shift; cmd_setup "$@" ;;
    start) cmd_start ;;
    stop) cmd_stop ;;
    update) cmd_update ;;
    backup) cmd_backup ;;
    export) shift; cmd_export "$@" ;;
    import) shift; cmd_import "$@" ;;
    logs) cmd_logs ;;
    uninstall) cmd_uninstall "${2:-}" ;;
    version) cmd_version ;;
    -h|--help|help|"") usage ;;
    *) echo "unknown command: ${1:-}" >&2; usage; exit 2 ;;
esac
