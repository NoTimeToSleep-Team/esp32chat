#!/bin/bash
# Health check for systemd
# Run: ./healthcheck.sh /opt/local-chat-server
BASE="${1:-/opt/local-chat-server}"
RESPONSE=$(curl -sf http://localhost:8000/health 2>/dev/null)
if [ -z "$RESPONSE" ]; then
    echo "HEALTHCHECK_FAIL: no response from /health"
    exit 1
fi
echo "HEALTHCHECK_OK: $RESPONSE"
exit 0
