#!/usr/bin/env bash
# lc — команды обслуживания Local Chat Server (v0.1).
# Устанавливается симлинком в /usr/local/bin/lc (см. install_pi.sh).
#
#   lc status    — служба + health-проверка
#   lc setup     — повторить мастер настройки (sudo)
#   lc update    — обновиться новым релизным тарболом (данные и настройки сохраняются)
#   lc backup    — архив data/ и app.env
#   lc logs      — журнал установки + журнал службы
#   lc uninstall — остановить и удалить (данные сохраняются; --purge удаляет всё)
#   lc version   — версия сервера
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/local-chat-server}"
SERVICE_NAME="local-chat-server"
ENV_FILE="${APP_ROOT}/config/app.env"
INSTALL_LOG="/var/log/lc-install.log"

require_root() {
    if [[ "${EUID}" -ne 0 ]]; then
        echo "Нужен root: sudo lc $1" >&2
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
    echo "  версия: $(cmd_version)"
    if systemd_ok; then
        echo "  служба: $(systemctl is-active ${SERVICE_NAME})"
    else
        echo "  служба: systemd недоступен"
    fi
    echo "  порт:   $(port)"
    if curl -fsS "http://127.0.0.1:$(port)/health" >/dev/null 2>&1; then
        echo "  health: ok (http://127.0.0.1:$(port)/health)"
    else
        echo "  health: НЕ ОТВЕЧАЕТ"
    fi
}

cmd_setup() {
    require_root setup
    if [[ ! -f "${APP_ROOT}/setup/wizard.sh" ]]; then
        echo "Мастер не найден: ${APP_ROOT}/setup/wizard.sh" >&2
        exit 1
    fi
    exec bash "${APP_ROOT}/setup/wizard.sh" "$@"
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
    lc_log "скачиваю новый релиз…"
    LC_PKG_ROOT="$(lc_fetch_release "${LC_WORK}")"

    lc_log "обновляю код (data/ и app.env сохраняются)"
    SOURCE_ROOT="${LC_PKG_ROOT}/server" \
        bash "${LC_PKG_ROOT}/server/scripts/install_pi.sh" --no-setup
    lc_log "обновление завершено: $(cmd_version)"
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
    echo "Бэкап создан: ${out}"
}

cmd_logs() {
    echo "=== журнал установки (${INSTALL_LOG}) ==="
    if [[ -f "${INSTALL_LOG}" ]]; then
        tail -n 80 "${INSTALL_LOG}"
    else
        echo "(пусто)"
    fi
    echo ""
    echo "=== служба ${SERVICE_NAME} (последние 100 строк) ==="
    if systemd_ok; then
        journalctl -u "${SERVICE_NAME}" -n 100 --no-pager 2>/dev/null || true
    else
        tail -n 100 "${APP_ROOT}/data/logs/smoke-server.log" 2>/dev/null || echo "(нет журнала)"
    fi
}

cmd_uninstall() {
    require_root uninstall
    local purge=0
    [[ "${1:-}" == "--purge" ]] && purge=1

    echo "Удаление Local Chat Server из ${APP_ROOT}"
    if [[ "${purge}" != "1" ]]; then
        echo "Данные (${APP_ROOT}/data) будут сохранены."
    fi
    read -r -p "Точно? Введите yes: " answer
    [[ "${answer}" == "yes" ]] || { echo "Отменено"; exit 0; }

    if systemd_ok; then
        systemctl stop "${SERVICE_NAME}" 2>/dev/null || true
        systemctl disable "${SERVICE_NAME}" 2>/dev/null || true
    fi
    rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
    systemctl daemon-reload 2>/dev/null || true
    rm -f /usr/local/bin/lc

    if [[ "${purge}" == "1" ]]; then
        rm -rf "${APP_ROOT}"
        echo "Удалено полностью (включая данные)."
    else
        mv "${APP_ROOT}" "${APP_ROOT}.removed-$(date +%Y%m%d-%H%M%S)"
        echo "Код удалён; данные сохранены в ${APP_ROOT}.removed-*"
    fi
}

usage() {
    cat <<EOF
lc — управление Local Chat Server
  lc status          состояние службы и портала
  lc setup           мастер настройки (sudo lc setup)
  lc update          обновить на новый релиз (sudo)
  lc backup          бэкап данных и настроек (sudo)
  lc logs            журналы
  lc uninstall       удалить (sudo; данные сохраняются)
  lc uninstall --purge  удалить полностью, включая данные (sudo)
  lc version         версия сервера
EOF
}

case "${1:-}" in
    status) cmd_status ;;
    setup) shift; cmd_setup "$@" ;;
    update) cmd_update ;;
    backup) cmd_backup ;;
    logs) cmd_logs ;;
    uninstall) cmd_uninstall "${2:-}" ;;
    version) cmd_version ;;
    -h|--help|help|"") usage ;;
    *) echo "неизвестная команда: ${1:-}" >&2; usage; exit 2 ;;
esac
