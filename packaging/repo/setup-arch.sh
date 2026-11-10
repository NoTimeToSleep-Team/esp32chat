#!/bin/sh
# Add the Local Chat pacman repository and install the package.
#
#   curl -fsSL https://notimetosleep-team.github.io/esp32chat/setup-arch.sh | sudo sh
#
# After this one-time bootstrap the standard commands work:
#   sudo pacman -S local-chat
#   sudo pacman -Syu
set -eu

BASE="${LC_REPO_URL:-https://notimetosleep-team.github.io/esp32chat}"
KEYFILE="/tmp/local-chat-repo-key.gpg"

if [ "$(id -u)" -ne 0 ]; then
    echo "[local-chat] run as root: curl -fsSL ${BASE}/setup-arch.sh | sudo sh" >&2
    exit 1
fi

command -v curl >/dev/null 2>&1 || {
    echo "[local-chat] curl is required: pacman -S curl" >&2
    exit 1
}

echo "[local-chat] importing the repository key"
curl -fsSL "${BASE}/local-chat.gpg" -o "${KEYFILE}"
pacman-key --add "${KEYFILE}"
FPR="$(gpg --show-keys --with-colons "${KEYFILE}" | awk -F: '/^fpr:/ {print $10; exit}')"
if [ -z "${FPR}" ]; then
    echo "[local-chat] could not read the key fingerprint" >&2
    exit 1
fi
pacman-key --lsign-key "${FPR}"
rm -f "${KEYFILE}"

if ! grep -q '^\[localchat\]' /etc/pacman.conf; then
    echo "[local-chat] adding the [localchat] repository to /etc/pacman.conf"
    cat >> /etc/pacman.conf <<EOF

[localchat]
SigLevel = Optional DatabaseOptional
Server = ${BASE}/arch/\$arch
EOF
fi

echo "[local-chat] installing local-chat"
pacman -Syu --noconfirm local-chat

echo
echo "[local-chat] installed. Next:"
echo "  sudo lc setup     — create the administrator and configure the server"
echo "  lc status         — check the service"
