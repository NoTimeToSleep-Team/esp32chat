#!/usr/bin/env bash
# LC v0.1 — мастер настройки (whiptail), schema-driven.
#
# Поля, дефолты, валидация и порядок экранов берутся из settings-schema.json
# (через manifest.py). Новый параметр сервера = новая запись в манифесте;
# этот скрипт не меняется.
#
# Режимы:
#   интерактивный  — whiptail-окна (Esc на любом шаге = отмена без изменений)
#   --preseed FILE — значения из файла KEY=VALUE, без вопросов (для автотестов)
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/local-chat-server}"
SERVICE_NAME="local-chat-server"
ENV_FILE="${APP_ROOT}/config/app.env"
SETUP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST_PY="${SETUP_DIR}/manifest.py"
SCHEMA_FILE="${SETUP_DIR}/settings-schema.json"
LC_LANG="${LC_LANG:-ru}"
PRESEED_FILE=""
TITLE="Local Chat Server — настройка"

log() { echo "[lc-wizard] $*"; }
fail() { log "ОШИБКА: $*"; exit 1; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --preseed) PRESEED_FILE="${2:?нужен путь к файлу после --preseed}"; shift 2 ;;
        -h|--help) echo "usage: sudo wizard.sh [--preseed FILE]"; exit 0 ;;
        *) fail "неизвестный аргумент: $1" ;;
    esac
done

[[ "${EUID}" -eq 0 ]] || fail "нужен root: sudo lc setup"
[[ -f "${MANIFEST_PY}" ]] || fail "не найден ${MANIFEST_PY}"
command -v python3 >/dev/null 2>&1 || fail "нужен python3"

INTERACTIVE=0
if command -v whiptail >/dev/null 2>&1 && [[ -t 0 ]]; then
    INTERACTIVE=1
fi

VALUES_FILE="$(mktemp)"
trap 'rm -f "${VALUES_FILE}"' EXIT

val() { grep "^$1=" "${VALUES_FILE}" 2>/dev/null | tail -1 | cut -d= -f2-; }
set_val() {
    sed -i "/^$1=/d" "${VALUES_FILE}" 2>/dev/null || true
    printf '%s=%s\n' "$1" "$2" >> "${VALUES_FILE}"
}

current_env_value() { sed -n "s/^$1=//p" "${ENV_FILE}" 2>/dev/null | tail -1; }
preseed_value() {
    if [[ -n "${PRESEED_FILE}" && -f "${PRESEED_FILE}" ]]; then
        sed -n "s/^$1=//p" "${PRESEED_FILE}" 2>/dev/null | tail -1
    fi
}

bool_yes() {
    case "${1:-}" in 1|true|yes|on|да) return 0 ;; *) return 1 ;; esac
}

cancel() {
    log "Отменено. Настройки не менялись."
    exit 130
}

validate() {
    python3 "${MANIFEST_PY}" validate "$1" "$2" 2>&1
}

# ---- исходные значения: preseed > app.env > дефолт из манифеста ----
while IFS=$'\x1f' read -r key type section label default choices required_if confirm persist; do
    cur="$(preseed_value "${key}")"
    [[ -n "${cur}" ]] || cur="$(current_env_value "${key}")"
    [[ -n "${cur}" ]] || cur="${default}"
    set_val "${key}" "${cur}"
done < <(python3 "${MANIFEST_PY}" fields "${LC_LANG}")

if [[ "${INTERACTIVE}" == "1" ]]; then
    whiptail --title "${TITLE}" --msgbox \
        "Добро пожаловать!\n\nУстановка завершена. Сейчас настроим портал:\n— администратор;\n— точка доступа Wi-Fi;\n— порт и режим регистрации.\n\nEsc на любом шаге — отмена без изменений." \
        15 68 </dev/tty || cancel
fi

# ---- экраны по полям манифеста ----
while IFS=$'\x1f' read -r key type section label default choices required_if confirm persist; do
    if [[ -n "${required_if}" && "${required_if}" != "-" ]]; then
        if ! bool_yes "$(val "${required_if}")"; then
            log "пропускаю ${key} (условие ${required_if}=нет)"
            continue
        fi
    fi
    cur="$(val "${key}")"

    if [[ "${INTERACTIVE}" != "1" ]]; then
        # неинтерактивный режим: просто проверяем, что значения корректны
        if [[ "${type}" == "bool" ]]; then
            if bool_yes "${cur}"; then cur="yes"; else cur="no"; fi
            set_val "${key}" "${cur}"
        else
            err="$(validate "${key}" "${cur}")" || fail "${label}: ${err}"
        fi
        log "значение: ${key}=${cur}"
        continue
    fi

    case "${type}" in
        bool)
            default_flag=""
            if ! bool_yes "${cur}"; then default_flag="--defaultno"; fi
            # shellcheck disable=SC2086
            whiptail --title "${TITLE}" ${default_flag} --yesno "${label}?" 7 64 </dev/tty
            rc=$?
            [[ ${rc} -eq 255 ]] && cancel
            if [[ ${rc} -eq 0 ]]; then cur="yes"; else cur="no"; fi
            set_val "${key}" "${cur}"
            ;;
        password)
            out="$(whiptail --title "${TITLE}" --passwordbox "${label}" 10 64 \
                3>&1 1>&2 2>&3 </dev/tty)" || cancel
            if [[ "${confirm}" == "1" ]]; then
                out2="$(whiptail --title "${TITLE}" --passwordbox "${label} (ещё раз)" 10 64 \
                    3>&1 1>&2 2>&3 </dev/tty)" || cancel
                if [[ "${out}" != "${out2}" ]]; then
                    whiptail --title "${TITLE}" --msgbox "Пароли не совпадают, повторите." 8 50 </dev/tty
                    continue
                fi
            fi
            if ! err="$(validate "${key}" "${out}")"; then
                whiptail --title "${TITLE}" --msgbox "Недопустимое значение: ${err}" 9 60 </dev/tty
                continue
            fi
            set_val "${key}" "${out}"
            ;;
        choice)
            args=()
            while IFS=$'\x1f' read -r cvalue clabel; do
                args+=("${cvalue}" "${clabel}")
            done < <(python3 "${MANIFEST_PY}" choices "${key}" "${LC_LANG}")
            out="$(whiptail --title "${TITLE}" --menu "${label}" 0 0 0 \
                --default-item "${cur}" "${args[@]}" 3>&1 1>&2 2>&3 </dev/tty)" || cancel
            set_val "${key}" "${out}"
            ;;
        *)
            # text / int
            out="$(whiptail --title "${TITLE}" --inputbox "${label}" 10 64 "${cur}" \
                3>&1 1>&2 2>&3 </dev/tty)" || cancel
            if ! err="$(validate "${key}" "${out}")"; then
                whiptail --title "${TITLE}" --msgbox "Недопустимое значение: ${err}" 9 60 </dev/tty
                continue
            fi
            set_val "${key}" "${out}"
            ;;
    esac
done < <(python3 "${MANIFEST_PY}" fields "${LC_LANG}")

# ---- перекрёстная проверка: AP включена -> нужен пароль точки ----
if bool_yes "$(val AP_ENABLED)"; then
    err="$(validate AP_PASSPHRASE "$(val AP_PASSPHRASE)")" \
        || fail "точка доступа включена, но пароль Wi-Fi некорректен: ${err}"
fi

# ---- сводка ----
summary() {
    local lines=()
    while IFS=$'\x1f' read -r key type section label default choices required_if confirm persist; do
        if [[ "${type}" == "password" ]]; then
            lines+=("${label}: ***")
        else
            lines+=("${label}: $(val "${key}")")
        fi
    done < <(python3 "${MANIFEST_PY}" fields "${LC_LANG}")
    printf '%s\n' "${lines[@]}"
}

if [[ "${INTERACTIVE}" == "1" ]]; then
    whiptail --title "${TITLE}" --scrollbox "$(summary)" 22 72 </dev/tty
    whiptail --title "${TITLE}" --yesno "Применить эти настройки?" 7 60 </dev/tty || cancel
else
    log "Сводка:"
    summary | sed 's/^/  /'
fi

# ---- применение ----
PY_CMD="${APP_ROOT}/.venv/bin/python"
[[ -x "${PY_CMD}" ]] || PY_CMD="python3"

log "сохраняю настройки в ${ENV_FILE}"
mkdir -p "$(dirname "${ENV_FILE}")"
touch "${ENV_FILE}"
while IFS=$'\x1f' read -r key type section label default choices required_if confirm persist; do
    [[ "${persist}" == "1" ]] || continue
    value="$(val "${key}")"
    [[ -n "${value}" ]] || continue
    python3 "${MANIFEST_PY}" set-env "${ENV_FILE}" "${key}" "${value}"
done < <(python3 "${MANIFEST_PY}" fields "${LC_LANG}")
chmod 600 "${ENV_FILE}"

log "создаю администратора"
( cd "${APP_ROOT}" \
  && "${PY_CMD}" -m app.cli --app-root "${APP_ROOT}" --env-file "${ENV_FILE}" \
      create-admin --username "$(val ADMIN_USERNAME)" --password "$(val ADMIN_PASSWORD)" ) \
    || fail "не удалось создать администратора"

if [[ -n "$(val LC_REGISTRATION_MODE)" ]]; then
    log "режим регистрации: $(val LC_REGISTRATION_MODE)"
    ( cd "${APP_ROOT}" \
      && "${PY_CMD}" -m app.cli --app-root "${APP_ROOT}" --env-file "${ENV_FILE}" \
          set-mode --mode "$(val LC_REGISTRATION_MODE)" ) \
        || fail "не удалось установить режим регистрации"
fi

# CLI писал в data/ от root — вернуть владение служебному пользователю,
# иначе сервис (localchat) не сможет писать в БД после рестарта.
chown -R "${APP_USER:-localchat}:${APP_GROUP:-localchat}" "${APP_ROOT}/data"

if bool_yes "$(val AP_ENABLED)"; then
    log "настраиваю точку доступа Wi-Fi"
    if AP_SSID="$(val AP_SSID)" AP_PASSPHRASE="$(val AP_PASSPHRASE)" \
        AP_CHANNEL="$(val AP_CHANNEL)" AP_COUNTRY="$(val AP_COUNTRY)" \
        bash "${APP_ROOT}/scripts/configure_pi_ap_nat.sh"; then
        log "точка доступа настроена: $(val AP_SSID)"
    else
        log "ВНИМАНИЕ: точка доступа не настроилась (нет Wi-Fi адаптера или hostapd не поднялся). Портал продолжит работать по проводной сети."
    fi
else
    log "точка доступа выключена"
fi

if command -v systemctl >/dev/null 2>&1 && [[ -d /run/systemd/system ]]; then
    systemctl daemon-reload
    systemctl restart "${SERVICE_NAME}" \
        || log "ВНИМАНИЕ: не удалось перезапустить службу ${SERVICE_NAME}"
fi

# ---- финал ----
IP="$(hostname -I 2>/dev/null | awk '{print $1}')" || IP=""
PORT="$(val LCS_PORT)"
AP_LINE="выключена"
if bool_yes "$(val AP_ENABLED)"; then AP_LINE="$(val AP_SSID)"; fi

MSG="Готово!

Портал: http://${IP:-127.0.0.1}:${PORT}
Логин администратора: $(val ADMIN_USERNAME)
Точка доступа Wi-Fi: ${AP_LINE}

Управление:
  lc status   — состояние
  lc setup    — повторить настройку
  lc logs     — журналы"

if [[ "${INTERACTIVE}" == "1" ]]; then
    whiptail --title "${TITLE}" --msgbox "${MSG}" 18 72 </dev/tty
else
    log "${MSG}"
fi

if [[ -n "${PRESEED_FILE}" ]]; then
    log "ВНИМАНИЕ: ${PRESEED_FILE} содержит пароли — удалите файл после настройки."
fi
