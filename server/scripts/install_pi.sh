#!/usr/bin/env bash
set -euo pipefail

APP_USER="${APP_USER:-localchat}"
APP_GROUP="${APP_GROUP:-localchat}"
APP_ROOT="${APP_ROOT:-/opt/local-chat-server}"
SERVICE_NAME="local-chat-server"
DISABLE_DEFAULT_NGINX_SITE="${DISABLE_DEFAULT_NGINX_SITE:-1}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1/health}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

VENV_PATH="${APP_ROOT}/.venv"
ENV_FILE="${APP_ROOT}/config/app.env"
SYSTEMD_DST="/etc/systemd/system/${SERVICE_NAME}.service"
NGINX_AVAIL="/etc/nginx/sites-available/${SERVICE_NAME}.conf"
NGINX_ENABLED="/etc/nginx/sites-enabled/${SERVICE_NAME}.conf"

if [[ "${EUID}" -ne 0 ]]; then
    echo "Run as root: sudo bash ${0}"
    exit 1
fi

log() {
    echo "[install_pi] $*"
}

sync_dir() {
    local src="$1"
    local dst="$2"
    mkdir -p "${dst}"
    rsync -a --delete "${src}/" "${dst}/"
}

log "Installing required packages"
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv python3-pip nginx rsync curl

if ! getent group "${APP_GROUP}" >/dev/null; then
    log "Creating group ${APP_GROUP}"
    groupadd --system "${APP_GROUP}"
fi

if ! id -u "${APP_USER}" >/dev/null 2>&1; then
    log "Creating user ${APP_USER}"
    useradd --system --gid "${APP_GROUP}" --home "${APP_ROOT}" --shell /usr/sbin/nologin "${APP_USER}"
fi

log "Syncing server sources to ${APP_ROOT}"
mkdir -p "${APP_ROOT}"
sync_dir "${SOURCE_ROOT}/app" "${APP_ROOT}/app"
sync_dir "${SOURCE_ROOT}/migrations" "${APP_ROOT}/migrations"
sync_dir "${SOURCE_ROOT}/config" "${APP_ROOT}/config"
sync_dir "${SOURCE_ROOT}/scripts" "${APP_ROOT}/scripts"
sync_dir "${SOURCE_ROOT}/systemd" "${APP_ROOT}/systemd"
sync_dir "${SOURCE_ROOT}/docs" "${APP_ROOT}/docs"
install -m 0644 "${SOURCE_ROOT}/pyproject.toml" "${APP_ROOT}/pyproject.toml"
install -m 0644 "${SOURCE_ROOT}/README.md" "${APP_ROOT}/README.md"

for directory in sqlite media avatars uploads rfid backups logs incidents; do
    mkdir -p "${APP_ROOT}/data/${directory}"
done

log "Preparing Python environment"
python3 -m venv "${VENV_PATH}"
"${VENV_PATH}/bin/python" -m pip install --upgrade pip wheel
"${VENV_PATH}/bin/pip" install -e "${APP_ROOT}"

if [[ ! -f "${ENV_FILE}" ]]; then
    log "Creating config from pi.env.example"
    cp "${APP_ROOT}/config/pi.env.example" "${ENV_FILE}"
fi

log "Installing systemd unit"
install -m 0644 "${APP_ROOT}/systemd/${SERVICE_NAME}.service" "${SYSTEMD_DST}"

log "Installing nginx site"
install -m 0644 "${APP_ROOT}/config/nginx/${SERVICE_NAME}.conf" "${NGINX_AVAIL}"
ln -sfn "${NGINX_AVAIL}" "${NGINX_ENABLED}"
if [[ "${DISABLE_DEFAULT_NGINX_SITE}" == "1" ]]; then
    rm -f /etc/nginx/sites-enabled/default
fi

chown -R "${APP_USER}:${APP_GROUP}" "${APP_ROOT}"

log "Reloading services"
nginx -t
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"
systemctl enable nginx
systemctl restart nginx

log "Waiting for health endpoint"
for attempt in $(seq 1 20); do
    if curl -fsS "${HEALTH_URL}" >/dev/null; then
        log "Deployment complete and health check passed"
        exit 0
    fi
    sleep 1
    log "Health check retry ${attempt}/20"
done

log "Health check failed, showing service status"
systemctl --no-pager --full status "${SERVICE_NAME}" || true
exit 1
