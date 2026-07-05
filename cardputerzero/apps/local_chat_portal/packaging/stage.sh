#!/usr/bin/env bash
set -euo pipefail

install -D -m 0755 launch_local_chat_portal.sh "$STAGE$APP_INSTALL_DIR/launch_local_chat_portal.sh"
install -D -m 0644 packaging/local-chat-portal.svg "$STAGE$APP_INSTALL_DIR/share/images/local-chat-portal.svg"

tmp=$(mktemp)
cat >"$tmp" <<'EOF'
#!/bin/sh
cd /usr/share/APPLaunch/apps/local-chat-portal-cz
exec ./launch_local_chat_portal.sh "$@"
EOF
install -D -m 0755 "$tmp" "$STAGE$INSTALL_PREFIX/bin/local-chat-portal"
rm -f "$tmp"
