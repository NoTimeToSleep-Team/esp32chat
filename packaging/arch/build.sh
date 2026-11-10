#!/usr/bin/env bash
# Build the local-chat pacman package (pkg.tar.zst).
#
# Usage:
#   WHEELS_DIR=/path/to/wheels [VERSION=0.1.10] [OUT_DIR=/path/to/dist] \
#     bash packaging/arch/build.sh
#
# Run inside an Arch Linux environment (base-devel + fakeroot). makepkg
# refuses to run as root, so when invoked as root the script creates a
# throwaway "builder" user (CI containers).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${HERE}/../.." && pwd)"
SERVER="${REPO_ROOT}/server"

WHEELS_DIR="${WHEELS_DIR:?set WHEELS_DIR to the wheel directory}"
OUT_DIR="${OUT_DIR:-${REPO_ROOT}/dist}"
VERSION="${VERSION:-$(sed -n 's/^__version__ = "\([^"]*\)"/\1/p' "${SERVER}/app/version.py" | head -1)}"
[ -n "${VERSION}" ] || { echo "cannot read the version from app/version.py" >&2; exit 1; }

log() { echo "[arch] $*" >&2; }

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

log "staging the payload"
bash "${HERE}/../common/stage.sh" "${WORK}/payload" "${WHEELS_DIR}"
sed "s|@VERSION@|${VERSION}|g" "${HERE}/PKGBUILD.in" > "${WORK}/PKGBUILD"
cp "${HERE}/local-chat.install" "${WORK}/local-chat.install"

run_makepkg() {
    ( cd "${WORK}" && makepkg --noconfirm --nodeps )
}

if [ "$(id -u)" -eq 0 ]; then
    log "running makepkg as an unprivileged build user"
    if ! id builder >/dev/null 2>&1; then
        useradd -m builder
    fi
    chown -R builder:builder "${WORK}"
    runuser -u builder -- bash -c "cd '${WORK}' && makepkg --noconfirm --nodeps"
else
    run_makepkg
fi

mkdir -p "${OUT_DIR}"
cp "${WORK}"/*.pkg.tar.zst "${OUT_DIR}/"
log "built: $(ls "${OUT_DIR}/local-chat-${VERSION}"-1-*.pkg.tar.zst 2>/dev/null | tr '\n' ' ')"
