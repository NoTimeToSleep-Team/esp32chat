#!/usr/bin/env bash
# Включает ТЕСТОВУЮ версию интерфейса на этом сервере.
#
# Рабочий интерфейс НЕ удаляется: он сохраняется рядом как templates/index.html.orig,
# поэтому откат делается одной командой — disable.sh.
#
# Запуск (на сервере): sudo bash enable.sh
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/local-chat-server}"
TPL="${APP_ROOT}/app/templates/index.html"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/index.html"

[[ -f "${SRC}" ]] || { echo "не найден тестовый интерфейс: ${SRC}" >&2; exit 1; }
[[ -f "${TPL}" ]] || { echo "не найден рабочий интерфейс: ${TPL}" >&2; exit 1; }

if [[ ! -f "${TPL}.orig" ]]; then
    cp -p "${TPL}" "${TPL}.orig"
    echo "бэкап рабочего интерфейса: ${TPL}.orig"
else
    echo "бэкап уже есть: ${TPL}.orig (не перезаписываю)"
fi

cp "${SRC}" "${TPL}"
echo "тестовый интерфейс включён — открой портал: http://<адрес-сервера>:18080/"
echo "откат к рабочему интерфейсу: sudo bash disable.sh"
