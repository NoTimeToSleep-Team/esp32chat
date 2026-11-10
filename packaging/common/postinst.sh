#!/usr/bin/env bash
# Local Chat — shared post-install / post-upgrade routine for all package
# formats (deb, rpm, pacman).
#
# Usage: postinst.sh <deb|rpm|pacman> <install|upgrade>
#
# Reproduces the curl installer's behaviour without network access:
#   service user + data dirs -> offline venv from bundled wheels ->
#   app.env + session secret -> systemd (or a one-off smoke run) ->
#   setup wizard on a fresh interactive install.
set -euo pipefail

CHANNEL="${1:-deb}"
ACTION="${2:-install}"

APP_ROOT="/opt/local-chat-server"
APP_USER="localchat"
APP_GROUP="localchat"
SERVICE_NAME="local-chat-server"
VENV="${APP_ROOT}/.venv"
ENV_FILE="${APP_ROOT}/config/app.env"
WHEELS="/usr/share/local-chat-server/wheels"
INSTALL_LOG="/var/log/lc-install.log"

log()  { echo "[local-chat] $*"; }
warn() { echo "[local-chat] WARNING: $*" >&2; }
die()  { echo "[local-chat] ERROR: $*" >&2; exit 1; }

if [ -d /var/log ] && [ -w /var/log ]; then
    exec > >(tee -a "${INSTALL_LOG}") 2>&1
fi

has_systemd() { command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; }
bool_yes() { case "${1:-}" in 1|true|yes|on) return 0 ;; *) return 1 ;; esac; }
port_now() { sed -n 's/^LCS_PORT=//p' "${ENV_FILE}" 2>/dev/null | tail -1 || true; }

# ---- 1. service account ----------------------------------------------------
if ! getent group "${APP_GROUP}" >/dev/null 2>&1; then
    log "creating the service group ${APP_GROUP}"
    groupadd --system "${APP_GROUP}"
fi
if ! id -u "${APP_USER}" >/dev/null 2>&1; then
    log "creating the service user ${APP_USER}"
    useradd --system --gid "${APP_GROUP}" --home "${APP_ROOT}" \
        --shell /usr/sbin/nologin "${APP_USER}"
fi

# ---- 2. data layout --------------------------------------------------------
for dir in sqlite media avatars uploads rfid backups logs incidents; do
    mkdir -p "${APP_ROOT}/data/${dir}"
done
chown -R "${APP_USER}:${APP_GROUP}" "${APP_ROOT}/data"
chmod 0755 "${APP_ROOT}"

# ---- 3. Python environment (offline, from the bundled wheels) -------------
PY3="$(command -v python3 || true)"
[ -n "${PY3}" ] || die "python3 is required but not installed"
"${PY3}" -c 'import venv' >/dev/null 2>&1 \
    || die "the python3 'venv' module is missing (install the python3-venv package)"

recreate=0
if [ ! -x "${VENV}/bin/python" ]; then
    recreate=1
else
    v_venv="$("${VENV}/bin/python" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo broken)"
    v_sys="$("${PY3}" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
    [ "${v_venv}" = "${v_sys}" ] || recreate=1
fi
if [ "${recreate}" = "1" ]; then
    log "creating the Python environment"
    rm -rf "${VENV}"
    "${PY3}" -m venv "${VENV}" || die "failed to create the virtualenv"
fi

WHEEL="$(find "${WHEELS}" -maxdepth 1 -name 'local_chat_server-*.whl' 2>/dev/null | sort -V | tail -1)"
[ -n "${WHEEL}" ] || die "the application wheel is missing from ${WHEELS}"
log "installing Python dependencies from the bundled wheels (offline)"
"${VENV}/bin/python" -m pip install --quiet --disable-pip-version-check \
    --no-index --find-links "${WHEELS}" --force-reinstall "${WHEEL}" \
    || die "pip install from the bundled wheels failed"

# ---- 4. configuration (app.env) -------------------------------------------
mkdir -p "${APP_ROOT}/config"
touch "${ENV_FILE}"

merge_env() {
    local key="$1" value="$2"
    grep -q "^${key}=" "${ENV_FILE}" || printf '%s=%s\n' "${key}" "${value}" >> "${ENV_FILE}"
}

while IFS='=' read -r key value; do
    [ -n "${key}" ] || continue
    value="${value//\$APP_ROOT/${APP_ROOT}}"
    merge_env "${key}" "${value}"
done < <(python3 "${APP_ROOT}/setup/manifest.py" base_env)

while IFS='=' read -r key value; do
    [ -n "${key}" ] || continue
    merge_env "${key}" "${value}"
done < <(python3 "${APP_ROOT}/setup/manifest.py" defaults)

if ! grep -q '^LCS_SESSION_SECRET=.\{16,\}' "${ENV_FILE}"; then
    SECRET="$(openssl rand -hex 32 2>/dev/null || python3 -c 'import secrets; print(secrets.token_hex(32))')"
    sed -i '/^LCS_SESSION_SECRET=/d' "${ENV_FILE}"
    printf 'LCS_SESSION_SECRET=%s\n' "${SECRET}" >> "${ENV_FILE}"
    log "generated a new session secret"
fi

if grep -q '^LC_INSTALL_CHANNEL=' "${ENV_FILE}"; then
    sed -i "s/^LC_INSTALL_CHANNEL=.*/LC_INSTALL_CHANNEL=${CHANNEL}/" "${ENV_FILE}"
else
    printf 'LC_INSTALL_CHANNEL=%s\n' "${CHANNEL}" >> "${ENV_FILE}"
fi
chmod 600 "${ENV_FILE}"
chown root:root "${ENV_FILE}"

# ---- 5. setup wizard, collect phase (fresh interactive install only) ------
WIZARD_RAN=0
if [ "${ACTION}" = "install" ] && [ -z "${LC_NO_WIZARD:-}" ] \
    && [ "${DEBIAN_FRONTEND:-}" != "noninteractive" ] \
    && [ -f "${APP_ROOT}/setup/wizard.sh" ] && command -v whiptail >/dev/null 2>&1 \
    && { : </dev/tty; } 2>/dev/null; then
    log "starting the setup wizard"
    if bash "${APP_ROOT}/setup/wizard.sh" --collect; then
        WIZARD_RAN=1
    else
        warn "the setup wizard was cancelled — configure later with: sudo lc setup"
    fi
fi

PORT="$(port_now)"
PORT="${PORT:-18080}"

# ---- 6. service ------------------------------------------------------------
if has_systemd; then
    systemctl daemon-reload
    systemctl unmask "${SERVICE_NAME}" >/dev/null 2>&1 || true
    if systemctl is-active --quiet "${SERVICE_NAME}"; then
        systemctl restart "${SERVICE_NAME}"
    else
        systemctl start "${SERVICE_NAME}"
    fi

    AUTOSTART="$(sed -n 's/^LC_AUTOSTART=//p' "${ENV_FILE}" | tail -1 || true)"
    case "${AUTOSTART}" in
        0|false|no|off)
            systemctl disable "${SERVICE_NAME}" >/dev/null 2>&1 || true
            ;;
        *)
            systemctl enable "${SERVICE_NAME}" >/dev/null 2>&1 || true
            ;;
    esac

    health=0
    for _ in $(seq 1 30); do
        if curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
            health=1
            break
        fi
        sleep 1
    done
    if [ "${health}" != "1" ]; then
        systemctl --no-pager --full status "${SERVICE_NAME}" >&2 || true
        die "the server did not answer on http://127.0.0.1:${PORT}/health — see: journalctl -u ${SERVICE_NAME} -n 50"
    fi
    log "service is running: http://127.0.0.1:${PORT}/health"
else
    log "systemd is not available — running a one-off smoke check"
    mkdir -p "${APP_ROOT}/data/logs"
    (
        cd "${APP_ROOT}"
        "${VENV}/bin/uvicorn" app.main:app --host 127.0.0.1 --port "${PORT}" \
            > "${APP_ROOT}/data/logs/smoke-server.log" 2>&1 &
        echo $! > "${APP_ROOT}/data/logs/smoke-server.pid"
    )
    health=0
    for _ in $(seq 1 30); do
        if curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
            health=1
            break
        fi
        sleep 1
    done
    if [ -f "${APP_ROOT}/data/logs/smoke-server.pid" ]; then
        kill "$(cat "${APP_ROOT}/data/logs/smoke-server.pid")" 2>/dev/null || true
        rm -f "${APP_ROOT}/data/logs/smoke-server.pid"
    fi
    # the smoke run wrote as root — hand the data back to the service user
    chown -R "${APP_USER}:${APP_GROUP}" "${APP_ROOT}/data"
    if [ "${health}" != "1" ]; then
        tail -n 40 "${APP_ROOT}/data/logs/smoke-server.log" >&2 || true
        die "the server did not pass the smoke check"
    fi
    log "smoke check passed"
fi

# ---- 7. setup wizard, apply phase -----------------------------------------
if [ "${WIZARD_RAN}" = "1" ]; then
    if ! bash "${APP_ROOT}/setup/wizard.sh" --apply; then
        warn "could not apply the setup answers — run: sudo lc setup"
    fi
fi

# ---- 8. drop artefacts of a previous curl install -------------------------
if [ -L /usr/local/bin/lc ] && [ "$(readlink /usr/local/bin/lc)" = "${APP_ROOT}/scripts/lc.sh" ]; then
    rm -f /usr/local/bin/lc
fi

# ---- 9. summary ------------------------------------------------------------
IP="$(hostname -I 2>/dev/null | awk '{print $1}')" || IP=""
PORT="$(port_now)"
PORT="${PORT:-18080}"
log "${CHANNEL} package: ${ACTION} complete"
log "  portal:  http://${IP:-127.0.0.1}:${PORT}"
log "  service: systemctl status ${SERVICE_NAME}"
if [ "${WIZARD_RAN}" != "1" ]; then
    log "  setup:   sudo lc setup   (create the administrator and configure the server)"
fi
