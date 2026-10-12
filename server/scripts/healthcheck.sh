#!/bin/bash
# Health check for systemd.
# Run: ./healthcheck.sh /opt/local-chat-server [PORT]
# Port берётся из config/app.env (LCS_PORT) или из второго аргумента.
BASE="${1:-/opt/local-chat-server}"
PORT="${2:-}"
if [[ -z "${PORT}" && -f "${BASE}/config/app.env" ]]; then
    PORT="$(sed -n 's/^LCS_PORT=//p' "${BASE}/config/app.env" | tail -1)"
fi
PORT="${PORT:-18080}"
RESPONSE=$(curl -sf "http://localhost:${PORT}/health" 2>/dev/null)
if [ -z "$RESPONSE" ]; then
    echo "HEALTHCHECK_FAIL: no response from /health (port ${PORT})"
    exit 1
fi
echo "HEALTHCHECK_OK: $RESPONSE"
exit 0
