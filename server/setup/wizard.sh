#!/usr/bin/env bash
# LC v0.1 — setup wizard (whiptail), schema-driven.
#
# Fields, defaults, validation and the screen order come from
# settings-schema.json (via manifest.py). A new server setting = a new manifest
# entry; this script does not change.
#
# Modes:
#   interactive   — whiptail dialogs (Esc on any step cancels without changes)
#   --preseed F   — values from a KEY=VALUE file, no prompts (for automation)
#
# Phases (the installer runs collect → install → apply):
#   --collect     — ask/validate/save the answers, write config/app.env,
#                   store every answer in config/wizard-answers.env, exit
#   --apply       — load the saved answers and create the admin, set the mode,
#                   configure the AP, enable autostart, restart the service
#   (no phase)    — collect + apply in one go (used by: sudo lc setup)
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/local-chat-server}"
SERVICE_NAME="local-chat-server"
ENV_FILE="${APP_ROOT}/config/app.env"
SETUP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST_PY="${SETUP_DIR}/manifest.py"
SCHEMA_FILE="${SETUP_DIR}/settings-schema.json"
PRESEED_FILE=""
PHASE="all"
TITLE="Local Chat Server — Setup"

log() { echo "[lc-wizard] $*"; }
fail() { log "ERROR: $*"; exit 1; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --preseed) PRESEED_FILE="${2:?path required after --preseed}"; shift 2 ;;
        --collect) PHASE="collect"; shift ;;
        --apply) PHASE="apply"; shift ;;
        -h|--help) echo "usage: sudo wizard.sh [--preseed FILE] [--collect|--apply]"; exit 0 ;;
        *) fail "unknown argument: $1" ;;
    esac
done

[[ "${EUID}" -eq 0 ]] || fail "root required: sudo lc setup"
[[ -f "${MANIFEST_PY}" ]] || fail "not found: ${MANIFEST_PY}"
command -v python3 >/dev/null 2>&1 || fail "python3 is required"

INTERACTIVE=0
# A preseed file always means non-interactive: apply the values without asking.
# Otherwise use whiptail when the process has a controlling terminal — this
# also works for the documented one-liner (curl … | sudo bash), where stdin is
# the pipe but /dev/tty is still the user's terminal.
if [[ -z "${PRESEED_FILE}" ]] && command -v whiptail >/dev/null 2>&1; then
    if { : </dev/tty; } 2>/dev/null; then
        INTERACTIVE=1
    fi
fi

VALUES_FILE="$(mktemp)"
ANSWERS_FILE="${APP_ROOT}/config/wizard-answers.env"
trap 'rm -f "${VALUES_FILE}"' EXIT

val() { grep "^$1=" "${VALUES_FILE}" 2>/dev/null | tail -1 | cut -d= -f2- || true; }
set_val() {
    sed -i "/^$1=/d" "${VALUES_FILE}" 2>/dev/null || true
    printf '%s=%s\n' "$1" "$2" >> "${VALUES_FILE}"
}

# NOTE: every value helper must end with "|| true": with set -e + pipefail a
# missing file (app.env does not exist yet during a fresh install) fails the
# pipeline and would kill the script silently.
current_env_value() { sed -n "s/^$1=//p" "${ENV_FILE}" 2>/dev/null | tail -1 || true; }
preseed_value() {
    if [[ -n "${PRESEED_FILE}" && -f "${PRESEED_FILE}" ]]; then
        sed -n "s/^$1=//p" "${PRESEED_FILE}" 2>/dev/null | tail -1 || true
    fi
}

bool_yes() {
    case "${1:-}" in 1|true|yes|on) return 0 ;; *) return 1 ;; esac
}

cancel() {
    log "Cancelled. Nothing was changed."
    exit 130
}

validate() {
    python3 "${MANIFEST_PY}" validate "$1" "$2" 2>&1
}

# ---- initial values: saved answers (apply) / preseed > app.env > default ----
if [[ "${PHASE}" == "apply" ]]; then
    [[ -f "${ANSWERS_FILE}" ]] || fail "no collected answers found (${ANSWERS_FILE}) — run: sudo lc setup"
    # The answers contain the password — remove the file as soon as we exit.
    trap 'rm -f "${VALUES_FILE}" "${ANSWERS_FILE}"' EXIT
    while IFS='=' read -r k v; do
        [[ -n "${k}" ]] || continue
        set_val "${k}" "${v}"
    done < "${ANSWERS_FILE}"
else
    while IFS=$'\x1f' read -r key type section label default choices required_if confirm persist; do
        cur="$(preseed_value "${key}")"
        [[ -n "${cur}" ]] || cur="$(current_env_value "${key}")"
        [[ -n "${cur}" ]] || cur="${default}"
        set_val "${key}" "${cur}"
    done < <(python3 "${MANIFEST_PY}" fields en)
fi

if [[ "${INTERACTIVE}" == "1" && "${PHASE}" != "apply" ]]; then
    welcome_text="Welcome!\n\nLet's configure the portal first:\n- administrator account;\n- Wi-Fi access point;\n- port and registration mode.\n\nThe server is installed right after this.\nPress Esc on any step to cancel without changes."
    if [[ "${PHASE}" == "all" ]]; then
        welcome_text="Welcome!\n\nLet's configure the portal:\n- administrator account;\n- Wi-Fi access point;\n- port and registration mode.\n\nThe current values are offered as defaults.\nPress Esc on any step to cancel without changes."
    fi
    whiptail --title "${TITLE}" --msgbox "${welcome_text}" 16 68 </dev/tty || cancel
fi

# ---- collect: one screen per manifest field ----
if [[ "${PHASE}" != "apply" ]]; then
while IFS=$'\x1f' read -r key type section label default choices required_if confirm persist; do
    if [[ -n "${required_if}" && "${required_if}" != "-" ]]; then
        if [[ "${required_if}" == *=* ]]; then
            # condition of the form KEY=value (e.g. LC_DATA_MODE=import)
            cond_key="${required_if%%=*}"
            cond_val="${required_if#*=}"
            if [[ "$(val "${cond_key}")" != "${cond_val}" ]]; then
                log "skipping ${key} (condition ${required_if} not met)"
                continue
            fi
        elif ! bool_yes "$(val "${required_if}")"; then
            log "skipping ${key} (condition ${required_if}=no)"
            continue
        fi
    fi
    cur="$(val "${key}")"

    if [[ "${INTERACTIVE}" != "1" ]]; then
        # non-interactive mode: only validate the values
        if [[ "${type}" == "bool" ]]; then
            if bool_yes "${cur}"; then cur="yes"; else cur="no"; fi
            set_val "${key}" "${cur}"
        else
            err="$(validate "${key}" "${cur}")" || fail "${label}: ${err}"
        fi
        log "value: ${key}=${cur}"
        continue
    fi

    case "${type}" in
        bool)
            default_flag=""
            if ! bool_yes "${cur}"; then default_flag="--defaultno"; fi
            # shellcheck disable=SC2086
            whiptail --title "${TITLE}" ${default_flag} --yesno "${label}?" 8 70 </dev/tty
            rc=$?
            [[ ${rc} -eq 255 ]] && cancel
            if [[ ${rc} -eq 0 ]]; then cur="yes"; else cur="no"; fi
            set_val "${key}" "${cur}"
            ;;
        password)
            out="$(whiptail --title "${TITLE}" --passwordbox "${label}" 10 64 \
                3>&1 1>&2 2>&3 </dev/tty)" || cancel
            if [[ "${confirm}" == "1" ]]; then
                out2="$(whiptail --title "${TITLE}" --passwordbox "${label} (repeat)" 10 64 \
                    3>&1 1>&2 2>&3 </dev/tty)" || cancel
                if [[ "${out}" != "${out2}" ]]; then
                    whiptail --title "${TITLE}" --msgbox "Passwords do not match, try again." 8 50 </dev/tty
                    continue
                fi
            fi
            if ! err="$(validate "${key}" "${out}")"; then
                whiptail --title "${TITLE}" --msgbox "Invalid value: ${err}" 9 60 </dev/tty
                continue
            fi
            set_val "${key}" "${out}"
            ;;
        choice)
            args=()
            while IFS=$'\x1f' read -r cvalue clabel; do
                args+=("${cvalue}" "${clabel}")
            done < <(python3 "${MANIFEST_PY}" choices "${key}" en)
            out="$(whiptail --title "${TITLE}" --menu "${label}" 0 0 0 \
                --default-item "${cur}" "${args[@]}" 3>&1 1>&2 2>&3 </dev/tty)" || cancel
            set_val "${key}" "${out}"
            ;;
        *)
            # text / int
            out="$(whiptail --title "${TITLE}" --inputbox "${label}" 10 64 "${cur}" \
                3>&1 1>&2 2>&3 </dev/tty)" || cancel
            if ! err="$(validate "${key}" "${out}")"; then
                whiptail --title "${TITLE}" --msgbox "Invalid value: ${err}" 9 60 </dev/tty
                continue
            fi
            set_val "${key}" "${out}"
            ;;
    esac
done < <(python3 "${MANIFEST_PY}" fields en)

# ---- cross-check: AP enabled -> a valid Wi-Fi password is required ----
if bool_yes "$(val AP_ENABLED)"; then
    err="$(validate AP_PASSPHRASE "$(val AP_PASSPHRASE)")" \
        || fail "the access point is enabled, but the Wi-Fi password is invalid: ${err}"
fi

# ---- cross-check: import mode -> the export file must exist and look right ----
if [[ "$(val LC_DATA_MODE)" == "import" ]]; then
    IMPORT_FILE="$(val LC_IMPORT_FILE)"
    [[ -n "${IMPORT_FILE}" ]] || fail "an export file path is required when starting from an export"
    [[ -f "${IMPORT_FILE}" ]] || fail "the export file does not exist: ${IMPORT_FILE}"
    IMPORT_LISTING="$(tar -tzf "${IMPORT_FILE}" 2>/dev/null || true)"
    if ! grep -q '^data/sqlite/' <<< "${IMPORT_LISTING}"; then
        fail "this does not look like an LC export file: ${IMPORT_FILE}"
    fi
fi

# ---- summary ----
summary() {
    local lines=()
    while IFS=$'\x1f' read -r key type section label default choices required_if confirm persist; do
        if [[ "${type}" == "password" ]]; then
            lines+=("${label}: ***")
        else
            lines+=("${label}: $(val "${key}")")
        fi
    done < <(python3 "${MANIFEST_PY}" fields en)
    printf '%s\n' "${lines[@]}"
}

if [[ "${INTERACTIVE}" == "1" ]]; then
    whiptail --title "${TITLE}" --scrollbox "$(summary)" 22 72 </dev/tty
    whiptail --title "${TITLE}" --yesno "Apply these settings?" 7 60 </dev/tty || cancel
else
    log "Summary:"
    summary | sed 's/^/  /'
fi
fi   # end of the collect phase

# ---- apply ----
PY_CMD="${APP_ROOT}/.venv/bin/python"
[[ -x "${PY_CMD}" ]] || PY_CMD="python3"

if [[ "${PHASE}" != "apply" ]]; then
log "saving settings to ${ENV_FILE}"
mkdir -p "$(dirname "${ENV_FILE}")"
touch "${ENV_FILE}"
while IFS=$'\x1f' read -r key type section label default choices required_if confirm persist; do
    [[ "${persist}" == "1" ]] || continue
    value="$(val "${key}")"
    [[ -n "${value}" ]] || continue
    python3 "${MANIFEST_PY}" set-env "${ENV_FILE}" "${key}" "${value}"
done < <(python3 "${MANIFEST_PY}" fields en)
chmod 600 "${ENV_FILE}"

# The install runs between the collect and apply phases — keep every answer
# (including the password, mode 600) for the apply step.
log "saving the collected answers"
mkdir -p "$(dirname "${ANSWERS_FILE}")"
: > "${ANSWERS_FILE}"
chmod 600 "${ANSWERS_FILE}"
while IFS=$'\x1f' read -r key type section label default choices required_if confirm persist; do
    printf '%s=%s\n' "${key}" "$(val "${key}")" >> "${ANSWERS_FILE}"
done < <(python3 "${MANIFEST_PY}" fields en)
if [[ "${PHASE}" == "all" ]]; then
    trap 'rm -f "${VALUES_FILE}" "${ANSWERS_FILE}"' EXIT
fi
fi

if [[ "${PHASE}" == "collect" ]]; then
    log "settings collected — continuing with the installation"
    exit 0
fi

IMPORT_OK=0
if [[ "$(val LC_DATA_MODE)" == "import" ]]; then
    log "importing the data from $(val LC_IMPORT_FILE)"
    if bash "${APP_ROOT}/scripts/lc.sh" import "$(val LC_IMPORT_FILE)" --yes; then
        IMPORT_OK=1
        log "data imported — the administrator and settings from the export are in use"
    else
        log "WARNING: the import failed — creating a clean administrator instead"
    fi
fi

if [[ "${IMPORT_OK}" != "1" ]]; then
    log "creating the administrator"
    ( cd "${APP_ROOT}" \
      && "${PY_CMD}" -m app.cli --app-root "${APP_ROOT}" --env-file "${ENV_FILE}" \
          create-admin --username "$(val ADMIN_USERNAME)" --password "$(val ADMIN_PASSWORD)" ) \
        || fail "failed to create the administrator"

    if [[ -n "$(val LC_REGISTRATION_MODE)" ]]; then
        log "registration mode: $(val LC_REGISTRATION_MODE)"
        ( cd "${APP_ROOT}" \
          && "${PY_CMD}" -m app.cli --app-root "${APP_ROOT}" --env-file "${ENV_FILE}" \
              set-mode --mode "$(val LC_REGISTRATION_MODE)" ) \
            || fail "failed to set the registration mode"
    fi
fi

# After a possible import the effective port comes from app.env.
EFFECTIVE_PORT="$(sed -n 's/^LCS_PORT=//p' "${ENV_FILE}" 2>/dev/null | tail -1 || true)"
[[ -n "${EFFECTIVE_PORT}" ]] || EFFECTIVE_PORT="$(val LCS_PORT)"

# The CLI wrote into data/ as root — return ownership to the service user,
# otherwise the server (localchat) cannot write the database after restart.
chown -R "${APP_USER:-localchat}:${APP_GROUP:-localchat}" "${APP_ROOT}/data"

if bool_yes "$(val AP_ENABLED)"; then
    log "configuring the Wi-Fi access point"
    if AP_SSID="$(val AP_SSID)" AP_PASSPHRASE="$(val AP_PASSPHRASE)" \
        AP_CHANNEL="$(val AP_CHANNEL)" AP_COUNTRY="$(val AP_COUNTRY)" \
        bash "${APP_ROOT}/scripts/configure_pi_ap_nat.sh"; then
        log "access point configured: $(val AP_SSID)"
    else
        log "WARNING: the access point did not configure (no Wi-Fi adapter?). The portal keeps working over Ethernet."
    fi
else
    log "access point disabled"
fi

if command -v systemctl >/dev/null 2>&1 && [[ -d /run/systemd/system ]]; then
    if bool_yes "$(val LC_AUTOSTART)"; then
        systemctl enable "${SERVICE_NAME}" >/dev/null 2>&1 || true
        log "autostart enabled"
    else
        systemctl disable "${SERVICE_NAME}" >/dev/null 2>&1 || true
        log "autostart disabled — start the server manually with: sudo lc start"
    fi
    systemctl daemon-reload
    systemctl unmask "${SERVICE_NAME}" >/dev/null 2>&1 || true
    systemctl restart "${SERVICE_NAME}" \
        || log "WARNING: failed to restart ${SERVICE_NAME}"
    # Wait briefly so "All done" is true: the server needs a few seconds.
    for _ in $(seq 1 20); do
        if curl -fsS "http://127.0.0.1:${EFFECTIVE_PORT}/health" >/dev/null 2>&1; then
            break
        fi
        sleep 1
    done
fi

# ---- done ----
IP="$(hostname -I 2>/dev/null | awk '{print $1}')" || IP=""
PORT="${EFFECTIVE_PORT}"
AP_LINE="disabled"
if bool_yes "$(val AP_ENABLED)"; then AP_LINE="$(val AP_SSID)"; fi
AUTOSTART_LINE="on boot"
if ! bool_yes "$(val LC_AUTOSTART)"; then AUTOSTART_LINE="manually (sudo lc start)"; fi

MSG="All done!

Portal: http://${IP:-127.0.0.1}:${PORT}
Administrator login: $(val ADMIN_USERNAME)
Wi-Fi access point: ${AP_LINE}
Server starts: ${AUTOSTART_LINE}

Management:
  lc status   — status
  lc setup    — re-run this wizard
  lc logs     — logs"

if [[ "${INTERACTIVE}" == "1" ]]; then
    whiptail --title "${TITLE}" --msgbox "${MSG}" 18 72 </dev/tty
else
    log "${MSG}"
fi

if [[ -n "${PRESEED_FILE}" ]]; then
    log "WARNING: ${PRESEED_FILE} contains passwords — delete the file after setup."
fi
