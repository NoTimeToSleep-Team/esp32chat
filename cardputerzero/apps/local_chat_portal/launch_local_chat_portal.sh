#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFERRED_BROWSER="${LOCAL_CHAT_BROWSER:-}"
MODE_SWITCH_PAGE="${SCRIPT_DIR}/mode_switch.html"

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

if [[ ! -f "${MODE_SWITCH_PAGE}" ]]; then
    log "mode switch page not found: ${MODE_SWITCH_PAGE}"
    exit 1
fi

BROWSER="$(pick_browser)" || {
    log "no supported browser found; set LOCAL_CHAT_BROWSER or install chromium/xdg-open"
    exit 1
}

TARGET_URL="file://${MODE_SWITCH_PAGE}"

case "${BROWSER}" in
    chromium|chromium-browser)
        exec "${BROWSER}" --app="${TARGET_URL}" --start-fullscreen --force-device-scale-factor=1
        ;;
    cog)
        exec "${BROWSER}" "${TARGET_URL}"
        ;;
    xdg-open)
        exec "${BROWSER}" "${TARGET_URL}"
        ;;
    *)
        exec "${BROWSER}" "${TARGET_URL}"
        ;;
esac
