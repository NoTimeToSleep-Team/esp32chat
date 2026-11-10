#!/usr/bin/env bash
# Build the local-chat .rpm package.
#
# Usage:
#   WHEELS_DIR=/path/to/wheels [VERSION=0.1.10] [OUT_DIR=/path/to/dist] \
#     bash packaging/rpm/build.sh
#
# Run inside a Fedora/RHEL environment (rpm-build + python3).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${HERE}/../.." && pwd)"
SERVER="${REPO_ROOT}/server"

WHEELS_DIR="${WHEELS_DIR:?set WHEELS_DIR to the wheel directory}"
OUT_DIR="${OUT_DIR:-${REPO_ROOT}/dist}"
VERSION="${VERSION:-$(sed -n 's/^__version__ = "\([^"]*\)"/\1/p' "${SERVER}/app/version.py" | head -1)}"
[ -n "${VERSION}" ] || { echo "cannot read the version from app/version.py" >&2; exit 1; }

log() { echo "[rpm] $*" >&2; }

TOP="$(mktemp -d)"
trap 'rm -rf "${TOP}"' EXIT
mkdir -p "${TOP}"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}

log "staging the payload"
bash "${HERE}/../common/stage.sh" "${TOP}/SOURCES/root" "${WHEELS_DIR}"

sed "s|@VERSION@|${VERSION}|g" "${HERE}/local-chat.spec.in" > "${TOP}/SPECS/local-chat.spec"

log "running rpmbuild"
rpmbuild -bb \
    --define "_topdir ${TOP}" \
    --define "dist %{nil}" \
    "${TOP}/SPECS/local-chat.spec"

mkdir -p "${OUT_DIR}"
find "${TOP}/RPMS" -name '*.rpm' -exec cp {} "${OUT_DIR}/" \;
log "built: $(ls "${OUT_DIR}"/local-chat-"${VERSION}"-1*.rpm 2>/dev/null | tr '\n' ' ')"
