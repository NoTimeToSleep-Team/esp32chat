#!/usr/bin/env bash
# LC v0.1 — server install/update engine (schema-driven).
#
# The engine does not hard-code settings: apt packages, base LCS_* environment,
# wizard fields and defaults come from server/setup/settings-schema.json via
# manifest.py. Re-running the engine = update; data/ and app.env are preserved.
#
# Usage:
#   sudo bash install_pi.sh [--no-setup] [--preseed FILE]
#   --no-setup  do not run the setup wizard after installing
#   --preseed F  take wizard values from a KEY=VALUE file
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
Install/update Local Chat Server (v0.1)
  sudo bash install_pi.sh [--no-setup] [--preseed FILE]
  --no-setup   do not run the setup wizard after installing
  --preseed F  take wizard values from a KEY=VALUE file
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-setup) SKIP_SETUP=1; shift ;;
        --preseed) PRESEED_FILE="${2:?path required after --preseed}"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "unknown argument: $1" >&2; usage; exit 2 ;;
    esac
done

# ---- logging and basic checks ----
if [[ -d /var/log && -w /var/log ]]; then
    exec > >(tee -a "${INSTALL_LOG}") 2>&1
fi
log() { echo "[lc-install] $(date '+%H:%M:%S') $*"; }
die() { log "ERROR: $*"; exit 1; }

[[ "${EUID}" -eq 0 ]] || die "root required: sudo bash $0"
[[ -f "${MANIFEST_PY}" ]] || die "manifest not found: ${MANIFEST_PY}"

# Only one install/update at a time: a second run would fight over the same
# files (rsync, pip, app.env) and can corrupt the virtualenv.
if [[ -d /run && -w /run ]] && command -v flock >/dev/null 2>&1; then
    exec 9>"/run/local-chat-install.lock"
    if ! flock -n 9; then
        die "another install or update is already running (/run/local-chat-install.lock). Wait for it to finish and re-run."
    fi
fi

# The manifest is read with python3, but python3 may be absent on a minimal
# system. In that case a bootstrap package list (same set as in the manifest)
# is used; after apt, everything runs through the manifest again.
FALLBACK_PACKAGES="python3 python3-venv python3-pip curl rsync whiptail ca-certificates openssl"

# ---- preflight: platform ----
# shellcheck disable=SC1091
. /etc/os-release 2>/dev/null || true
OS_ID="${ID:-}"
OS_VER="${VERSION_ID:-0}"
if [[ "${OS_ID}" != "debian" && "${OS_ID}" != "raspbian" ]]; then
    die "Raspberry Pi OS / Debian (64-bit) required. Found: ${PRETTY_NAME:-unknown system}"
fi
if (( ${OS_VER%%.*} < 12 )); then
    die "this OS (${PRETTY_NAME:-Debian ${OS_VER}}) is too old: the server needs Python >= ${MIN_PYTHON:-3.10}. Upgrade to Raspberry Pi OS Bookworm (Debian 12) 64-bit and re-run the installer."
fi

ARCH="$(uname -m)"
if [[ "${ARCH}" == "aarch64" || "${ARCH}" == "arm64" ]]; then
    log "platform: ARM 64-bit (Raspberry Pi)"
elif [[ "${ARCH}" == "x86_64" ]]; then
    log "WARNING: x86_64 is not a Raspberry Pi. Continuing, but this is a test/virtual environment."
else
    die "unsupported architecture: ${ARCH}"
fi

FREE_KB="$(df -Pk "$(dirname "${APP_ROOT}")" 2>/dev/null | awk 'NR==2 {print $4}')" || true
if [[ -n "${FREE_KB}" && "${FREE_KB}" -lt 300000 ]]; then
    die "not enough disk space (${FREE_KB} KB free, ~300 MB required)"
fi

# ---- apt self-heal (lock wait, stale-lock cleanup, retries) ----
apt_lock_stale() {
    # 0 — locks are absent or clearly stale (nobody holds them);
    # 1 — someone seems to be using apt right now.
    # fuser/pgrep reliably see live apt/dpkg processes (the installer runs as
    # root); the age heuristic is only a fallback when fuser is unavailable —
    # otherwise our own just-finished apt run looks "busy" for 2 minutes.
    local lock have_fuser=0
    command -v fuser >/dev/null 2>&1 && have_fuser=1
    for lock in /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock /var/lib/apt/lists/lock /var/cache/apt/archives/lock; do
        [[ -f "${lock}" ]] || continue
        if [[ "${have_fuser}" == "1" ]] && fuser "${lock}" >/dev/null 2>&1; then
            return 1
        fi
        # Match real apt/dpkg processes by name (comm), not by command line:
        # a command-line match (e.g. some log filter containing "dpkg ") would
        # keep the installer waiting for five minutes for nothing.
        if command -v pgrep >/dev/null 2>&1 \
            && pgrep -x 'apt|apt-get|aptitude|dpkg|dpkg-deb|dpkg-preconfigu|unattended-upgr' >/dev/null 2>&1; then
            return 1
        fi
        # no fuser available: fall back to the age heuristic
        if [[ "${have_fuser}" != "1" ]] \
            && [[ $(( $(date +%s) - $(stat -c %Y "${lock}" 2>/dev/null || echo 0) )) -lt 120 ]]; then
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
        log "apt is busy with another process (attempt ${i}/60) — waiting 5s"
        sleep 5
    done
    die "the apt lock was not released within 5 minutes. Wait for other apt processes to finish and re-run the installer."
}

apt_run() {
    local attempt
    for attempt in 1 2 3; do
        apt_wait
        # An interrupted dpkg (power loss, a kill) leaves a state apt refuses
        # to work with — finish the pending configuration first.
        if [[ -n "$(ls -A /var/lib/dpkg/updates 2>/dev/null)" ]] \
            || dpkg --audit 2>/dev/null | grep -q .; then
            log "dpkg has unfinished operations — running dpkg --configure -a"
            dpkg --configure -a >/dev/null 2>&1 || true
        fi
        if DEBIAN_FRONTEND=noninteractive apt-get -y -o DPkg::Lock::Timeout=300 "$@"; then
            return 0
        fi
        # A half-upgraded package family (e.g. python3.13 vs libpython3.13)
        # blocks every install with unmet dependencies — let apt settle it.
        if DEBIAN_FRONTEND=noninteractive apt-get -y --fix-broken install >/dev/null 2>&1; then
            log "apt dependencies settled (--fix-broken)"
        fi
        log "apt-get $* — attempt ${attempt} failed, retrying in 5s"
        sleep 5
    done
    die "apt-get $* failed after 3 attempts. Check the network/repositories and re-run."
}

log "updating package lists"
apt_run update

PACKAGES="${FALLBACK_PACKAGES}"
MIN_PYTHON="3.10"
if command -v python3 >/dev/null 2>&1; then
    PACKAGES="$(python3 "${MANIFEST_PY}" apt_packages)"
    MIN_PYTHON="$(python3 "${MANIFEST_PY}" min_python)"
else
    log "python3 is missing — installing the bootstrap package set"
fi
log "installing packages: ${PACKAGES}"
# shellcheck disable=SC2086
apt_run install ${PACKAGES}

# ---- self-heal: packages that are "installed" but actually broken ----
# A manually deleted binary (or a botched upgrade) leaves dpkg thinking the
# package is fine, so a plain "apt-get install" does nothing. Check the files
# and modules the installer relies on and force-reinstall what is missing.
#
# python3 comes first, and its files are restored directly: on Debian the
# apt-listchanges pre-install hook is a Python script, so a missing
# interpreter aborts every apt transaction — apt cannot repair python3.
# dpkg-deb extraction has no such hooks.
if ! python3 -c 'import sys' >/dev/null 2>&1; then
    log "python3 is not usable — restoring the interpreter files"
    PY_TMP="$(mktemp -d)"
    PY_PKGS="python3-minimal"
    for extra in $(dpkg -l 2>/dev/null | awk '/^ii/ && $2 ~ /^python3\.[0-9]+-minimal$/ {print $2}' || true); do
        PY_PKGS="${PY_PKGS} ${extra}"
    done
    for p in ${PY_PKGS}; do
        V="$(dpkg-query -W -f='${Version}' "${p}" 2>/dev/null)"
        ( cd "${PY_TMP}" && { apt-get download "${p}=${V}" 2>/dev/null || apt-get download "${p}"; } ) >/dev/null 2>&1 || true
    done
    for deb in "${PY_TMP}"/*.deb; do
        [[ -f "${deb}" ]] || continue
        dpkg-deb -x "${deb}" "${PY_TMP}/x" 2>/dev/null || true
    done
    if [[ -d "${PY_TMP}/x/usr/bin" ]]; then
        for f in "${PY_TMP}"/x/usr/bin/*; do
            b="$(basename "${f}")"
            [[ -e "/usr/bin/${b}" ]] || cp -a "${f}" "/usr/bin/${b}"
        done
        log "interpreter restored: $(python3 -V 2>&1 || echo 'still broken')"
    else
        log "WARNING: could not fetch the interpreter package — continuing"
    fi
    rm -rf "${PY_TMP}"
fi

SELFHEAL_PKGS="${PACKAGES} python3-minimal"
for extra in $(dpkg -l 2>/dev/null | awk '/^ii/ && $2 ~ /^python3\.[0-9]+(-minimal|-venv|-pip)?$/ {print $2}' || true); do
    SELFHEAL_PKGS="${SELFHEAL_PKGS} ${extra}"
done
REINSTALL=""
for pkg in ${SELFHEAL_PKGS}; do
    dpkg -s "${pkg}" >/dev/null 2>&1 || continue
    while read -r f; do
        [[ -e "${f}" ]] || REINSTALL="${REINSTALL} ${pkg}"
    done < <(dpkg -L "${pkg}" 2>/dev/null | grep -E '^/usr/(s?bin|games)/' || true)
done
if ! python3 -c 'import venv' >/dev/null 2>&1; then
    REINSTALL="${REINSTALL} python3-venv $(dpkg -l 2>/dev/null | awk '/^ii/ && $2 ~ /^python3\.[0-9]+-venv$/ {print $2}' || true)"
fi
if ! python3 -m pip --version >/dev/null 2>&1; then
    REINSTALL="${REINSTALL} python3-pip $(dpkg -l 2>/dev/null | awk '/^ii/ && $2 ~ /^python3\.[0-9]+-pip$/ {print $2}' || true)"
fi
[[ -s /etc/ssl/certs/ca-certificates.crt ]] || REINSTALL="${REINSTALL} ca-certificates"
REINSTALL="$(echo ${REINSTALL} | tr ' ' '\n' | sort -u | tr '\n' ' ')"
if [[ -n "${REINSTALL// /}" ]]; then
    log "repairing broken packages:${REINSTALL}"
    # shellcheck disable=SC2086
    apt_run install --reinstall ${REINSTALL} || true
fi

python3 -c 'import sys; p = sys.argv[1].split("."); sys.exit(0 if sys.version_info >= (int(p[0]), int(p[1]) if len(p) > 1 else 0) else 1)' "${MIN_PYTHON}" \
    || die "Python >= ${MIN_PYTHON} required, but $(python3 -V 2>&1) is installed. Upgrade the OS."

# ---- setup (collect) — BEFORE the install: the answers decide how we install,
# and a cancelled wizard leaves the system untouched ----
WIZARD_RAN=0
if [[ "${SKIP_SETUP}" == "1" ]]; then
    log "wizard skipped (--no-setup) — configure later with: sudo lc setup"
elif [[ -n "${PRESEED_FILE}" ]]; then
    log "applying the preseeded setup (no questions asked)"
    if bash "${SOURCE_ROOT}/setup/wizard.sh" --collect --preseed "${PRESEED_FILE}"; then
        WIZARD_RAN=1
    else
        log "preseeded setup failed — configure later with: sudo lc setup"
    fi
elif [[ -z "${LC_NO_WIZARD:-}" ]] && { : </dev/tty; } 2>/dev/null; then
    if [[ -f "${SOURCE_ROOT}/setup/wizard.sh" ]] && bash "${SOURCE_ROOT}/setup/wizard.sh" --collect; then
        WIZARD_RAN=1
    else
        log "setup wizard was cancelled or failed — configure later with: sudo lc setup"
    fi
else
    log "non-interactive mode — wizard skipped (run it later with: sudo lc setup)"
fi

# ---- service user ----
if ! getent group "${APP_GROUP}" >/dev/null; then
    groupadd --system "${APP_GROUP}"
fi
if ! id -u "${APP_USER}" >/dev/null 2>&1; then
    useradd --system --gid "${APP_GROUP}" --home "${APP_ROOT}" --shell /usr/sbin/nologin "${APP_USER}"
fi

# ---- layout at /opt/local-chat-server ----
log "laying out the code at ${APP_ROOT}"
mkdir -p "${APP_ROOT}"
for dir in app migrations scripts systemd setup; do
    [[ -d "${SOURCE_ROOT}/${dir}" ]] || die "no ${dir}/ in the source"
    mkdir -p "${APP_ROOT}/${dir}"
    rsync -a --delete \
        --exclude '__pycache__' --exclude '*.pyc' \
        "${SOURCE_ROOT}/${dir}/" "${APP_ROOT}/${dir}/"
done
mkdir -p "${APP_ROOT}/config"
rsync -a --delete \
    --exclude 'app.env' --exclude 'wizard-answers.env' \
    --exclude '__pycache__' --exclude '*.pyc' \
    "${SOURCE_ROOT}/config/" "${APP_ROOT}/config/"
install -m 0644 "${SOURCE_ROOT}/pyproject.toml" "${APP_ROOT}/pyproject.toml"
if [[ -f "${SOURCE_ROOT}/README.md" ]]; then
    install -m 0644 "${SOURCE_ROOT}/README.md" "${APP_ROOT}/README.md"
fi

for d in sqlite media avatars uploads rfid backups logs incidents; do
    mkdir -p "${APP_ROOT}/data/${d}"
done

# ---- venv and dependencies (with retries) ----
log "preparing the Python environment"
if [[ ! -x "${VENV_PATH}/bin/python" ]] \
    || ! "${VENV_PATH}/bin/python" -m pip --version >/dev/null 2>&1; then
    log "creating the Python virtualenv"
    rm -rf "${VENV_PATH}"
    python3 -m venv "${VENV_PATH}"
fi
"${VENV_PATH}/bin/python" -m pip install --upgrade pip wheel >/dev/null 2>&1 \
    || log "WARNING: failed to upgrade pip (continuing)"

PIP_OK=0
for attempt in 1 2 3; do
    if "${VENV_PATH}/bin/python" -m pip install --no-cache-dir "${APP_ROOT}"; then
        PIP_OK=1
        break
    fi
    log "pip install — attempt ${attempt} failed, retrying in 5s"
    sleep 5
done
[[ "${PIP_OK}" == "1" ]] || die "failed to install Python dependencies (3 attempts). Check the network and re-run."

# ---- app.env: base settings + field defaults + secret ----
log "generating ${ENV_FILE}"
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
    log "generated LCS_SESSION_SECRET"
fi
chmod 600 "${ENV_FILE}"
chown root:root "${ENV_FILE}"

PORT="$(sed -n 's/^LCS_PORT=//p' "${ENV_FILE}" | tail -1 || true)"
PORT="${PORT:-18080}"

# ---- ownership ----
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
    # A runtime mask (/run/systemd/system) would still block the start.
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
            log "autostart disabled — start the server manually with: sudo lc start"
            ;;
        *)
            systemctl enable "${SERVICE_NAME}" >/dev/null 2>&1 || true
            ;;
    esac
    SYSTEMD_OK=1
    log "service ${SERVICE_NAME} started"
else
    log "WARNING: systemd is not available (test environment?) — running a smoke check instead"
fi

# ---- health check ----
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
        log "health check passed: http://127.0.0.1:${PORT}/health"
    else
        log "health check failed; service status:"
        systemctl --no-pager --full status "${SERVICE_NAME}" || true
        die "the server did not answer on /health. Logs: journalctl -u ${SERVICE_NAME} -n 50"
    fi
else
    mkdir -p "${APP_ROOT}/data/logs"
    ( cd "${APP_ROOT}" \
        && nohup "${VENV_PATH}/bin/uvicorn" app.main:app --host 127.0.0.1 --port "${PORT}" --no-proxy-headers \
            > "${APP_ROOT}/data/logs/smoke-server.log" 2>&1 \
        & echo $! > "${APP_ROOT}/data/logs/smoke-server.pid" )
    if wait_health "http://127.0.0.1:${PORT}"; then
        log "smoke check passed: the server started and answered on /health"
    else
        log "smoke check log:"
        tail -n 40 "${APP_ROOT}/data/logs/smoke-server.log" || true
        die "the server did not answer on /health"
    fi
    kill "$(cat "${APP_ROOT}/data/logs/smoke-server.pid")" 2>/dev/null || true
fi

# ---- lc command ----
ln -sfn "${APP_ROOT}/scripts/lc.sh" /usr/local/bin/lc

# ---- setup (apply) — after the install: create the admin, set the mode, … ----
if [[ "${WIZARD_RAN}" == "1" ]]; then
    log "applying the setup answers"
    if bash "${APP_ROOT}/setup/wizard.sh" --apply; then
        log "setup finished"
    else
        log "applying the setup answers failed — configure later with: sudo lc setup"
    fi
fi

# ---- summary ----
IP="$(hostname -I 2>/dev/null | awk '{print $1}')" || IP=""
log "INSTALLATION COMPLETE"
log "  Portal:    http://${IP:-127.0.0.1}:${PORT}  (locally: http://127.0.0.1:${PORT})"
log "  Service:   systemctl status ${SERVICE_NAME}"
log "  Commands:  lc status | lc setup | lc logs | lc update | lc backup | lc uninstall"
