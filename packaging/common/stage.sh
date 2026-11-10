#!/usr/bin/env bash
# Stage the complete package root tree shared by the deb, rpm and pacman
# builds. The result is a filesystem tree that is copied verbatim into the
# package:
#
#   opt/local-chat-server/...              application + setup/ + systemd/
#   usr/share/local-chat-server/wheels/    offline Python wheels
#   usr/share/local-chat-server/postinst.sh
#   usr/lib/systemd/system/local-chat-server.service
#   usr/bin/lc -> /opt/local-chat-server/scripts/lc.sh
#   usr/share/doc/local-chat/              copyright + LICENSE
#
# Usage: stage.sh OUT_ROOT WHEELS_DIR
set -euo pipefail

OUT="${1:?usage: stage.sh OUT_ROOT WHEELS_DIR}"
WHEELS_DIR="${2:?usage: stage.sh OUT_ROOT WHEELS_DIR}"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${HERE}/../.." && pwd)"
SERVER="${REPO_ROOT}/server"
APP="${OUT}/opt/local-chat-server"

log() { echo "[stage] $*" >&2; }

rm -rf "${OUT}"
install -d "${APP}"

for dir in app migrations scripts setup systemd; do
    cp -a "${SERVER}/${dir}" "${APP}/"
done
install -m 0644 "${SERVER}/pyproject.toml" "${APP}/pyproject.toml"
if [ -f "${SERVER}/README.md" ]; then
    install -m 0644 "${SERVER}/README.md" "${APP}/README.md"
fi

# Checkout hygiene: caches out, LF endings, deterministic modes
find "${APP}" -type d -name '__pycache__' -prune -exec rm -rf {} +
find "${APP}" -type f -name '*.pyc' -delete
find "${APP}" -type f \( -name '*.sh' -o -name '*.py' -o -name '*.service' -o -name '*.json' \) \
    -exec sed -i 's/\r$//' {} +
find "${APP}" -type d -exec chmod 0755 {} +
find "${APP}" -type f -exec chmod 0644 {} +
chmod 0755 "${APP}/scripts/"*.sh "${APP}/setup/"*.sh

# Offline wheels + shared postinst helper
install -d "${OUT}/usr/share/local-chat-server/wheels"
cp "${WHEELS_DIR}/"*.whl "${OUT}/usr/share/local-chat-server/wheels/"
chmod 0644 "${OUT}/usr/share/local-chat-server/wheels/"*.whl
install -m 0755 "${HERE}/postinst.sh" "${OUT}/usr/share/local-chat-server/postinst.sh"

# systemd unit + management CLI
install -D -m 0644 "${SERVER}/systemd/local-chat-server.service" \
    "${OUT}/usr/lib/systemd/system/local-chat-server.service"
install -d "${OUT}/usr/bin"
ln -s ../../opt/local-chat-server/scripts/lc.sh "${OUT}/usr/bin/lc"

# Documentation
install -d "${OUT}/usr/share/doc/local-chat"
cat > "${OUT}/usr/share/doc/local-chat/copyright" <<'EOF'
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: Local Chat (esp32chat)
Source: https://github.com/NoTimeToSleep-Team/esp32chat
License: MIT
EOF
if [ -f "${REPO_ROOT}/LICENSE" ]; then
    install -m 0644 "${REPO_ROOT}/LICENSE" "${OUT}/usr/share/doc/local-chat/LICENSE"
fi

log "staged $(find "${OUT}" -type f | wc -l) files in ${OUT}"
