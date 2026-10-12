#!/usr/bin/env bash
# LC v0.1 — «вечная» команда установки. Не меняется после релиза.
#
# Два режима:
#   1) запущен из распакованного релиза (рядом лежит server/):
#      сразу запускает движок установки;
#   2) скачан отдельно (curl …/install.sh | sudo bash):
#      качает релизный тарбол, проверяет sha256, распаковывает и запускает движок.
#
# Переменные:
#   LC_VERSION=x.y.z   — установить конкретную версию
#   LC_TARBALL_URL=…   — свой URL/путь к тарболу (для тестов, офлайн-установки)
#   LC_REPO=org/repo   — репозиторий релизов (по умолчанию NoTimeToSleep-Team/esp32chat)
#
# Все аргументы передаются движку (--no-setup, --preseed …).
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Режим 1: запущен из репозитория (server/setup/install.sh) или из тарбола (корень).
if [[ -f "${SELF_DIR}/server/scripts/install_pi.sh" ]]; then
    export SOURCE_ROOT="${SELF_DIR}/server"
elif [[ -f "${SELF_DIR}/../scripts/install_pi.sh" ]]; then
    export SOURCE_ROOT="${SELF_DIR}/.."
else
    # Режим 2: скачиваем релиз.
    if [[ -f "${SELF_DIR}/server/setup/lib.sh" ]]; then
        . "${SELF_DIR}/server/setup/lib.sh"
    elif [[ -f "${SELF_DIR}/lib.sh" ]]; then
        . "${SELF_DIR}/lib.sh"
    else
        echo "ОШИБКА: рядом нет server/setup/lib.sh — скачан повреждённый файл" >&2
        exit 1
    fi

    WORK="$(mktemp -d)"
    trap 'rm -rf "${WORK}"' EXIT
    PKG_ROOT="$(lc_fetch_release "${WORK}")"
    export SOURCE_ROOT="${PKG_ROOT}/server"
fi

exec bash "${SOURCE_ROOT}/scripts/install_pi.sh" "$@"
