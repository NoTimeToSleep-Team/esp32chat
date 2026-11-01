#!/bin/sh
# Harden the installed server tree after a deploy.
#
# Application code, migrations and installer scripts are read-only to the
# service account.  Only the data directory is writable by localchat.
set -eu

ROOT="${1:-/opt/local-chat-server}"

if [ "$(id -u)" -ne 0 ]; then
    echo "harden_install_permissions.sh must run as root" >&2
    exit 1
fi
if [ ! -d "$ROOT/app" ] || [ ! -d "$ROOT/migrations" ]; then
    echo "not a local-chat-server tree: $ROOT" >&2
    exit 1
fi

# Remove group/other write from everything first.  This catches deploy
# archives created on filesystems without Unix modes (Windows tar uses 777).
chmod -R go-w "$ROOT"

# Code and migrations: root-owned, executable/read-only for the service.
chown -R root:root "$ROOT/app" "$ROOT/migrations" "$ROOT/scripts" "$ROOT/setup" "$ROOT/systemd"
find "$ROOT/app" "$ROOT/migrations" -type d -exec chmod 755 {} +
find "$ROOT/app" "$ROOT/migrations" -type f -exec chmod 644 {} +

# Scripts may be executed by root during maintenance, but never written by
# the service account.
find "$ROOT/scripts" -type d -exec chmod 755 {} +
find "$ROOT/scripts" -type f -name '*.sh' -exec chmod 755 {} +
find "$ROOT/scripts" -type f -name '*.py' -exec chmod 755 {} +
find "$ROOT/scripts" -type f ! -name '*.sh' ! -name '*.py' -exec chmod 644 {} +

# .venv must remain executable; remove only write access from group/other.
find "$ROOT/.venv" -type d -exec chmod go-w {} + 2>/dev/null || true
find "$ROOT/.venv" -type f -exec chmod go-w {} + 2>/dev/null || true

# Configuration contains secrets; localchat needs read access, not write.
chown root:localchat "$ROOT/config" "$ROOT/config/app.env"
chmod 750 "$ROOT/config"
chmod 640 "$ROOT/config/app.env"
find "$ROOT/config" -type f ! -name 'app.env' -exec chmod 644 {} +
find "$ROOT/systemd" -type f -exec chmod 644 {} +

# Runtime state is owned by the service account and not world-readable.
chown -R localchat:localchat "$ROOT/data"
find "$ROOT/data" -type d -exec chmod 750 {} +
find "$ROOT/data" -type f -exec chmod 640 {} +

chmod 755 "$ROOT"

remaining="$(find "$ROOT" -xdev \( -type f -o -type d \) \( -perm -o+w -o -perm -g+w \) -print | wc -l)"
if [ "$remaining" -ne 0 ]; then
    echo "still group/other-writable: $remaining path(s)" >&2
    find "$ROOT" -xdev \( -type f -o -type d \) \( -perm -o+w -o -perm -g+w \) -print | head -40 >&2
    exit 1
fi

echo "hardened: $ROOT"
