#!/usr/bin/env bash
# Возвращает рабочий интерфейс (восстанавливает templates/index.html из бэкапа).
#
# Запуск (на сервере): sudo bash disable.sh
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/local-chat-server}"
TPL="${APP_ROOT}/app/templates/index.html"

[[ -f "${TPL}.orig" ]] || { echo "нет бэкапа ${TPL}.orig — нечего восстанавливать" >&2; exit 1; }

cp -p "${TPL}.orig" "${TPL}"
echo "рабочий интерфейс восстановлен из ${TPL}.orig"
echo "проверка: http://<адрес-сервера>:18080/"
