#!/usr/bin/env bash
# Build the tiny noarch rpm that installs the dnf repository definition and
# imports the signing key.
#
# Usage:
#   BASE_URL=https://... KEY_FILE=/path/local-chat.gpg OUT_DIR=/path \
#     bash packaging/repo/build-release-rpm.sh
#
# Run in an environment with rpm-build (Fedora, or Ubuntu with the rpm package).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_URL="${BASE_URL:?set BASE_URL (public repository root)}"
KEY_FILE="${KEY_FILE:?set KEY_FILE (armored public key)}"
OUT_DIR="${OUT_DIR:?set OUT_DIR}"

TOP="$(mktemp -d)"
trap 'rm -rf "${TOP}"' EXIT
mkdir -p "${TOP}"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}

sed "s|@BASE_URL@|${BASE_URL}|g" "${HERE}/local-chat.repo.in" \
    > "${TOP}/SOURCES/local-chat.repo"
install -m 0644 "${KEY_FILE}" "${TOP}/SOURCES/local-chat.gpg"
cp "${HERE}/release-rpm/local-chat-release.spec" "${TOP}/SPECS/"

rpmbuild -bb \
    --define "_topdir ${TOP}" \
    --define "dist %{nil}" \
    "${TOP}/SPECS/local-chat-release.spec"

mkdir -p "${OUT_DIR}"
find "${TOP}/RPMS" -name '*.rpm' -exec cp {} "${OUT_DIR}/" \;
echo "[release-rpm] built: $(ls "${OUT_DIR}"/local-chat-release-*.rpm | tr '\n' ' ')"
