#!/bin/sh
# Add the Local Chat apt repository and install the package.
#
#   curl -fsSL https://notimetosleep-team.github.io/esp32chat/setup-apt.sh | sudo sh
#
# After this one-time bootstrap the standard commands work:
#   sudo apt install local-chat
#   sudo apt upgrade
set -eu

BASE="${LC_REPO_URL:-https://notimetosleep-team.github.io/esp32chat}"
KEYRING="/usr/share/keyrings/local-chat.gpg"

if [ "$(id -u)" -ne 0 ]; then
    echo "[local-chat] run as root: curl -fsSL ${BASE}/setup-apt.sh | sudo sh" >&2
    exit 1
fi

command -v curl >/dev/null 2>&1 || {
    echo "[local-chat] curl is required: apt-get install -y curl" >&2
    exit 1
}

echo "[local-chat] adding the apt repository"
curl -fsSL "${BASE}/local-chat.gpg" -o "${KEYRING}"
chmod 0644 "${KEYRING}"
echo "deb [signed-by=${KEYRING}] ${BASE}/apt stable main" \
    > /etc/apt/sources.list.d/local-chat.list

echo "[local-chat] updating package lists"
apt-get update -q

echo "[local-chat] installing local-chat"
apt-get install -y local-chat

echo
echo "[local-chat] installed. Next:"
echo "  sudo lc setup     — create the administrator and configure the server"
echo "  lc status         — check the service"
