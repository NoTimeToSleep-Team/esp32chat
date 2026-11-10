#!/usr/bin/env bash
# Build the local-chat .deb package.
#
# Usage:
#   ARCH=amd64|arm64 WHEELS_DIR=/path/to/wheels \
#     [VERSION=0.1.10] [OUT_DIR=/path/to/dist] \
#     bash packaging/deb/build.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${HERE}/../.." && pwd)"
SERVER="${REPO_ROOT}/server"

ARCH="${ARCH:?set ARCH (amd64 or arm64)}"
WHEELS_DIR="${WHEELS_DIR:?set WHEELS_DIR to the wheel directory}"
OUT_DIR="${OUT_DIR:-${REPO_ROOT}/dist}"
VERSION="${VERSION:-$(sed -n 's/^__version__ = "\([^"]*\)"/\1/p' "${SERVER}/app/version.py" | head -1)}"
[ -n "${VERSION}" ] || { echo "cannot read the version from app/version.py" >&2; exit 1; }

PKG="local-chat_${VERSION}-1_${ARCH}.deb"
log() { echo "[deb] $*" >&2; }

STAGE="$(mktemp -d)"
trap 'rm -rf "${STAGE}"' EXIT
R="${STAGE}/root"

log "staging ${PKG}"
bash "${HERE}/../common/stage.sh" "${R}" "${WHEELS_DIR}"

# Control metadata + maintainer scripts
install -d "${R}/DEBIAN"
sed -e "s|@VERSION@|${VERSION}-1|g" -e "s|@ARCH@|${ARCH}|g" \
    "${HERE}/control.in" > "${R}/DEBIAN/control"

cat > "${R}/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
case "${1:-configure}" in
    configure)
        if [ -n "${2:-}" ]; then
            /usr/share/local-chat-server/postinst.sh deb upgrade
        else
            /usr/share/local-chat-server/postinst.sh deb install
        fi
        ;;
esac
exit 0
EOF

cat > "${R}/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "deconfigure" ]; then
    if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
        systemctl stop local-chat-server >/dev/null 2>&1 || true
        systemctl disable local-chat-server >/dev/null 2>&1 || true
    fi
fi
exit 0
EOF

cat > "${R}/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
case "$1" in
    remove|purge)
        if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
            systemctl daemon-reload >/dev/null 2>&1 || true
        fi
        rm -rf /opt/local-chat-server/.venv
        ;;
esac
if [ "$1" = "purge" ]; then
    rm -rf /opt/local-chat-server/config
    echo "[local-chat] user data kept in /opt/local-chat-server/data (delete it manually to remove all data)" >&2
fi
exit 0
EOF

chmod 0755 "${R}/DEBIAN/postinst" "${R}/DEBIAN/prerm" "${R}/DEBIAN/postrm"

(
    cd "${R}"
    find . -type f ! -path './DEBIAN/*' -printf '%P\0' \
        | sort -z | xargs -0 md5sum > DEBIAN/md5sums
)

mkdir -p "${OUT_DIR}"
dpkg-deb --build --root-owner-group "${R}" "${OUT_DIR}/${PKG}" >/dev/null
log "built: ${OUT_DIR}/${PKG} ($(du -h "${OUT_DIR}/${PKG}" | cut -f1))"
