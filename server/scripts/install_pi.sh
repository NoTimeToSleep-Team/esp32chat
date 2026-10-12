#!/usr/bin/env bash
# LC v0.1 — движок установки/обновления сервера (schema-driven).
#
# Логика не зависит от конкретных настроек: apt-пакеты, базовые LCS_*-настройки,
# поля мастера и действия берутся из server/setup/settings-schema.json через
# manifest.py. Повторный запуск = обновление: данные (data/) и app.env не затираются.
#
# Использование:
#   sudo bash install_pi.sh [--no-setup] [--preseed FILE]
#   --no-setup  не запускать мастер настройки после установки
#   --preseed F  подставить значения мастера из файла KEY=VALUE
set -euo pipefail

APP_USER="${APP_USER:-localchat}"
APP_GROUP="${APP_GROUP:-localchat}"
APP_ROOT="${APP_ROOT:-/opt/local-chat-server}"
SERVICE_NAME="local-chat-server"
VENV_PATH="${APP_ROOT}/.venv"
ENV_FILE="${APP_ROOT}/config/app.env"
INSTALL_LOG="/var/log/lc-install.log"
SKIP_SETUP=0
PRESEED_FILE=""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="${SOURCE_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
SETUP_DIR="${SOURCE_ROOT}/setup"
MANIFEST_PY="${SETUP_DIR}/manifest.py"

usage() {
    cat <<EOF
Установка/обновление Local Chat Server (v0.1)
  sudo bash install_pi.sh [--no-setup] [--preseed FILE]
  --no-setup   не запускать мастер настройки после установки
  --preseed F  подставить значения мастера из файла KEY=VALUE
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-setup) SKIP_SETUP=1; shift ;;
        --preseed) PRESEED_FILE="${2:?нужен путь к файлу после --preseed}"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "неизвестный аргумент: $1" >&2; usage; exit 2 ;;
    esac
done

# ---- журнал и базовые проверки ----
if [[ -d /var/log && -w /var/log ]]; then
    exec > >(tee -a "${INSTALL_LOG}") 2>&1
fi
log() { echo "[lc-install] $(date '+%H:%M:%S') $*"; }
die() { log "ОШИБКА: $*"; exit 1; }

[[ "${EUID}" -eq 0 ]] || die "нужен root: sudo bash $0"
[[ -f "${MANIFEST_PY}" ]] || die "не найден манифест: ${MANIFEST_PY}"

# Манифест читается python3, но python3 может отсутствовать в минимальной системе.
# Тогда используется загрузочный список пакетов (тот же набор, что в манифесте);
# после apt python3 появится и дальше всё работает через манифест.
FALLBACK_PACKAGES="python3 python3-venv python3-pip curl rsync whiptail ca-certificates openssl"

# ---- preflight: платформа ----
# shellcheck disable=SC1091
. /etc/os-release 2>/dev/null || true
OS_ID="${ID:-}"
OS_VER="${VERSION_ID:-0}"
if [[ "${OS_ID}" != "debian" && "${OS_ID}" != "raspbian" ]]; then
    die "поддерживается Raspberry Pi OS / Debian (64-bit). Найдено: ${PRETTY_NAME:-неизвестная система}"
fi
if (( ${OS_VER%%.*} < 12 )); then
    die "эта ОС (${PRETTY_NAME:-Debian ${OS_VER}}) слишком старая: серверу нужен Python >= ${MIN_PYTHON}. Обновитесь до Raspberry Pi OS Bookworm (Debian 12) 64-bit и запустите установку снова."
fi

ARCH="$(uname -m)"
if [[ "${ARCH}" == "aarch64" || "${ARCH}" == "arm64" ]]; then
    log "платформа: ARM 64-bit (Raspberry Pi)"
elif [[ "${ARCH}" == "x86_64" ]]; then
    log "ВНИМАНИЕ: x86_64 — это не Raspberry Pi. Продолжаю, но это тестовая/виртуальная среда."
else
    die "неподдерживаемая архитектура: ${ARCH}"
fi

FREE_KB="$(df -Pk "$(dirname "${APP_ROOT}")" 2>/dev/null | awk 'NR==2 {print $4}')" || true
if [[ -n "${FREE_KB}" && "${FREE_KB}" -lt 300000 ]]; then
    die "мало места на диске (${FREE_KB} KB свободно, нужно ~300 MB)"
fi

# ---- самообслуживание apt (ожидание лока, повторы, уборка устаревших локов) ----
apt_lock_stale() {
    # 0 — локи либо отсутствуют, либо явно устаревшие (никто их не держит);
    # 1 — похоже, кто-то работает с apt прямо сейчас.
    local lock
    for lock in /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock /var/lib/apt/lists/lock /var/cache/apt/archives/lock; do
        [[ -f "${lock}" ]] || continue
        if command -v fuser >/dev/null 2>&1 && fuser "${lock}" >/dev/null 2>&1; then
            return 1
        fi
        if command -v pgrep >/dev/null 2>&1 \
            && pgrep -f 'apt-get|/usr/bin/apt |dpkg ' >/dev/null 2>&1; then
            return 1
        fi
        # локу больше 2 минут и никто его не держит — устаревший
        if [[ $(( $(date +%s) - $(stat -c %Y "${lock}" 2>/dev/null || echo 0) )) -lt 120 ]]; then
            return 1
        fi
    done
    return 0
}

apt_wait() {
    local i
    for i in $(seq 1 60); do
        if apt_lock_stale; then
            rm -f /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock \
                /var/lib/apt/lists/lock /var/cache/apt/archives/lock 2>/dev/null || true
            return 0
        fi
        log "apt занят другим процессом (попытка ${i}/60) — жду 5с"
        sleep 5
    done
    die "apt-lock не освободился за 5 минут. Дождитесь завершения других apt-процессов и повторите установку."
}

apt_run() {
    local attempt
    for attempt in 1 2 3; do
        apt_wait
        if DEBIAN_FRONTEND=noninteractive apt-get -y -o DPkg::Lock::Timeout=300 "$@"; then
            return 0
        fi
        log "apt-get $* — попытка ${attempt} не удалась, повтор через 5с"
        sleep 5
    done
    die "apt-get $* не удалось после 3 попыток. Проверьте сеть/репозитории и повторите."
}

log "обновляю списки пакетов"
apt_run update

PACKAGES="${FALLBACK_PACKAGES}"
MIN_PYTHON="3.10"
if command -v python3 >/dev/null 2>&1; then
    PACKAGES="$(python3 "${MANIFEST_PY}" apt_packages)"
    MIN_PYTHON="$(python3 "${MANIFEST_PY}" min_python)"
else
    log "python3 отсутствует — ставлю загрузочный набор пакетов"
fi
log "доустанавливаю пакеты: ${PACKAGES}"
# shellcheck disable=SC2086
apt_run install ${PACKAGES}

python3 -c 'import sys; p = sys.argv[1].split("."); sys.exit(0 if sys.version_info >= (int(p[0]), int(p[1]) if len(p) > 1 else 0) else 1)' "${MIN_PYTHON}" \
    || die "нужен Python >= ${MIN_PYTHON}, а установлен $(python3 -V 2>&1). Обновите ОС."

# ---- служебный пользователь ----
if ! getent group "${APP_GROUP}" >/dev/null; then
    groupadd --system "${APP_GROUP}"
fi
if ! id -u "${APP_USER}" >/dev/null 2>&1; then
    useradd --system --gid "${APP_GROUP}" --home "${APP_ROOT}" --shell /usr/sbin/nologin "${APP_USER}"
fi

# ---- раскладка в /opt/local-chat-server ----
log "раскладываю код в ${APP_ROOT}"
mkdir -p "${APP_ROOT}"
for dir in app migrations scripts systemd setup; do
    [[ -d "${SOURCE_ROOT}/${dir}" ]] || die "в источнике нет каталога ${dir}/"
    mkdir -p "${APP_ROOT}/${dir}"
    rsync -a --delete \
        --exclude '__pycache__' --exclude '*.pyc' \
        "${SOURCE_ROOT}/${dir}/" "${APP_ROOT}/${dir}/"
done
mkdir -p "${APP_ROOT}/config"
rsync -a --delete \
    --exclude 'app.env' --exclude '__pycache__' --exclude '*.pyc' \
    "${SOURCE_ROOT}/config/" "${APP_ROOT}/config/"
install -m 0644 "${SOURCE_ROOT}/pyproject.toml" "${APP_ROOT}/pyproject.toml"
if [[ -f "${SOURCE_ROOT}/README.md" ]]; then
    install -m 0644 "${SOURCE_ROOT}/README.md" "${APP_ROOT}/README.md"
fi

for d in sqlite media avatars uploads rfid backups logs incidents; do
    mkdir -p "${APP_ROOT}/data/${d}"
done

# ---- venv и зависимости (с повторами) ----
log "готовлю Python-окружение"
if [[ ! -x "${VENV_PATH}/bin/python" ]]; then
    python3 -m venv "${VENV_PATH}"
fi
"${VENV_PATH}/bin/python" -m pip install --upgrade pip wheel >/dev/null 2>&1 \
    || log "ВНИМАНИЕ: не удалось обновить pip (продолжаю)"

PIP_OK=0
for attempt in 1 2 3; do
    if "${VENV_PATH}/bin/python" -m pip install --no-cache-dir "${APP_ROOT}"; then
        PIP_OK=1
        break
    fi
    log "pip install — попытка ${attempt} не удалась, повтор через 5с"
    sleep 5
done
[[ "${PIP_OK}" == "1" ]] || die "не удалось установить зависимости Python (3 попытки). Проверьте сеть и повторите."

# ---- app.env: базовые настройки + дефолты полей + секрет ----
log "формирую ${ENV_FILE}"
mkdir -p "${APP_ROOT}/config"
touch "${ENV_FILE}"

merge_env() {
    local key="$1" value="$2"
    if grep -q "^${key}=" "${ENV_FILE}"; then
        return 0
    fi
    echo "${key}=${value}" >> "${ENV_FILE}"
}

while IFS='=' read -r key value; do
    [[ -n "${key}" ]] || continue
    value="${value//\$APP_ROOT/${APP_ROOT}}"
    merge_env "${key}" "${value}"
done < <(python3 "${MANIFEST_PY}" base_env)

while IFS='=' read -r key value; do
    [[ -n "${key}" ]] || continue
    merge_env "${key}" "${value}"
done < <(python3 "${MANIFEST_PY}" defaults)

if ! grep -q '^LCS_SESSION_SECRET=.\{16,\}' "${ENV_FILE}" \
    || grep -q '^LCS_SESSION_SECRET=\(dev-insecure\|replace-with\)' "${ENV_FILE}"; then
    SECRET="$(openssl rand -hex 32 2>/dev/null || python3 -c 'import secrets; print(secrets.token_hex(32))')"
    sed -i "/^LCS_SESSION_SECRET=/d" "${ENV_FILE}"
    echo "LCS_SESSION_SECRET=${SECRET}" >> "${ENV_FILE}"
    log "сгенерирован LCS_SESSION_SECRET"
fi
chmod 600 "${ENV_FILE}"
chown root:root "${ENV_FILE}"

PORT="$(sed -n 's/^LCS_PORT=//p' "${ENV_FILE}" | tail -1)"
PORT="${PORT:-18080}"

# ---- права ----
chown -R "${APP_USER}:${APP_GROUP}" "${APP_ROOT}/data"
chown -R root:root "${APP_ROOT}/app" "${APP_ROOT}/migrations" "${APP_ROOT}/scripts" \
    "${APP_ROOT}/systemd" "${APP_ROOT}/setup" "${APP_ROOT}/config"
chmod 0755 "${APP_ROOT}"

# ---- systemd ----
SYSTEMD_OK=0
if command -v systemctl >/dev/null 2>&1 && [[ -d /run/systemd/system ]]; then
    install -m 0644 "${SOURCE_ROOT}/systemd/${SERVICE_NAME}.service" \
        "/etc/systemd/system/${SERVICE_NAME}.service"
    systemctl daemon-reload
    if systemctl is-active --quiet "${SERVICE_NAME}"; then
        systemctl restart "${SERVICE_NAME}"
    else
        systemctl enable "${SERVICE_NAME}" >/dev/null 2>&1
        systemctl start "${SERVICE_NAME}"
    fi
    SYSTEMD_OK=1
    log "служба ${SERVICE_NAME} запущена"
else
    log "ВНИМАНИЕ: systemd недоступен (тестовая среда?) — проверю сервер смоук-прогоном"
fi

# ---- health-check ----
wait_health() {
    local base="$1" attempt
    for attempt in $(seq 1 30); do
        if curl -fsS "${base}/health" >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done
    return 1
}

if [[ "${SYSTEMD_OK}" == "1" ]]; then
    if wait_health "http://127.0.0.1:${PORT}"; then
        log "health-check прошёл: http://127.0.0.1:${PORT}/health"
    else
        log "health-check не прошёл; состояние службы:"
        systemctl --no-pager --full status "${SERVICE_NAME}" || true
        die "сервер не ответил на /health. Журнал: journalctl -u ${SERVICE_NAME} -n 50"
    fi
else
    mkdir -p "${APP_ROOT}/data/logs"
    ( cd "${APP_ROOT}" \
        && nohup "${VENV_PATH}/bin/uvicorn" app.main:app --host 127.0.0.1 --port "${PORT}" \
            > "${APP_ROOT}/data/logs/smoke-server.log" 2>&1 \
        & echo $! > "${APP_ROOT}/data/logs/smoke-server.pid" )
    if wait_health "http://127.0.0.1:${PORT}"; then
        log "смоук-прогон прошёл: сервер поднялся и ответил на /health"
    else
        log "журнал смоук-прогона:"
        tail -n 40 "${APP_ROOT}/data/logs/smoke-server.log" || true
        die "сервер не ответил на /health"
    fi
    kill "$(cat "${APP_ROOT}/data/logs/smoke-server.pid")" 2>/dev/null || true
fi

# ---- команда lc ----
ln -sfn "${APP_ROOT}/scripts/lc.sh" /usr/local/bin/lc

# ---- мастер настройки ----
if [[ "${SKIP_SETUP}" == "1" ]]; then
    log "мастер пропущен (--no-setup) — настройте позже: sudo lc setup"
elif [[ ! -t 0 || -n "${LC_NO_WIZARD:-}" ]]; then
    log "неинтерактивный режим — мастер пропущен (запустите: sudo lc setup)"
elif [[ -f "${APP_ROOT}/setup/wizard.sh" ]]; then
    if bash "${APP_ROOT}/setup/wizard.sh" ${PRESEED_FILE:+--preseed "${PRESEED_FILE}"}; then
        log "мастер завершён"
    else
        log "мастер отменён или завершился с ошибкой — настройте позже: sudo lc setup"
    fi
fi

# ---- итог ----
IP="$(hostname -I 2>/dev/null | awk '{print $1}')" || IP=""
log "УСТАНОВКА ЗАВЕРШЕНА"
log "  Портал:   http://${IP:-127.0.0.1}:${PORT}  (локально: http://127.0.0.1:${PORT})"
log "  Служба:   systemctl status ${SERVICE_NAME}"
log "  Команды:  lc status | lc setup | lc logs | lc update | lc backup | lc uninstall"
