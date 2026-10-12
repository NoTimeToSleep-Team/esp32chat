#!/usr/bin/env bash
# LC v0.1 — сборщик релизного тарбола сервера.
#
# В тарбол попадает только серверная часть: server/ (без data/, .venv/,
# __pycache__), плюс install.sh в корне пакета. firmware/, experiments/,
# school/, tests/ — вне релиза.
#
# Результат: dist/lc-server-v<версия>.tar.gz + dist/lc-server-v<версия>.tar.gz.sha256
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${SERVER_ROOT}/.." && pwd)"
OUT_DIR="${OUT_DIR:-${REPO_ROOT}/dist}"

VERSION_FILE="${SERVER_ROOT}/app/version.py"
[[ -f "${VERSION_FILE}" ]] || { echo "не найден ${VERSION_FILE}" >&2; exit 1; }
VERSION="$(sed -n 's/^__version__ = "\([^"]*\)"/\1/p' "${VERSION_FILE}" | head -1)"
[[ -n "${VERSION}" ]] || { echo "не удалось прочитать версию из ${VERSION_FILE}" >&2; exit 1; }

PKG="lc-server-v${VERSION}"
STAGE="$(mktemp -d)"
trap 'rm -rf "${STAGE}"' EXIT

mkdir -p "${STAGE}/${PKG}/server"
tar -C "${SERVER_ROOT}" -cf - \
    --exclude '.venv' \
    --exclude 'data' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude 'docs' \
    . | tar -C "${STAGE}/${PKG}/server" -xf -

# «вечная» команда установки в корне пакета (та же, что публикуется в GitHub Release)
install -m 0755 "${SERVER_ROOT}/setup/install.sh" "${STAGE}/${PKG}/install.sh"

mkdir -p "${OUT_DIR}"
tar -czf "${OUT_DIR}/${PKG}.tar.gz" -C "${STAGE}" "${PKG}"
( cd "${OUT_DIR}" && sha256sum "${PKG}.tar.gz" > "${PKG}.tar.gz.sha256" )

echo "Готово:"
echo "  ${OUT_DIR}/${PKG}.tar.gz"
echo "  ${OUT_DIR}/${PKG}.tar.gz.sha256"
