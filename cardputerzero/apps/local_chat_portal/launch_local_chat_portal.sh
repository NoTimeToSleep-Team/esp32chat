#!/usr/bin/env bash
set -euo pipefail

SERVER_URL="${LOCAL_CHAT_SERVER_URL:-http://127.0.0.1:8000/}"
PREFERRED_BROWSER="${LOCAL_CHAT_BROWSER:-}"

log() {
    printf '[local-chat-portal] %s\n' "$*" >&2
}

has_command() {
    command -v "$1" >/dev/null 2>&1
}

pick_browser() {
    if [[ -n "${PREFERRED_BROWSER}" ]]; then
        printf '%s\n' "${PREFERRED_BROWSER}"
        return 0
    fi

    for candidate in chromium-browser chromium cog xdg-open; do
        if has_command "${candidate}"; then
            printf '%s\n' "${candidate}"
            return 0
        fi
    done

    return 1
}

if has_command curl; then
    if ! curl -fsS --max-time 2 "${SERVER_URL%/}/health" >/dev/null 2>&1; then
        log "warning: health probe failed for ${SERVER_URL%/}/health; opening client anyway"
    fi
fi

BROWSER="$(pick_browser)" || {
    log "no supported browser found; set LOCAL_CHAT_BROWSER or install chromium/xdg-open"
    exit 1
}

case "${BROWSER}" in
    chromium|chromium-browser)
        exec "${BROWSER}" --app="${SERVER_URL}" --start-fullscreen --force-device-scale-factor=1
        ;;
    cog)
        exec "${BROWSER}" "${SERVER_URL}"
        ;;
    xdg-open)
        exec "${BROWSER}" "${SERVER_URL}"
        ;;
    *)
        exec "${BROWSER}" "${SERVER_URL}"
        ;;
esac
