#!/usr/bin/env bash
# LC v0.1 — one-command installer bootstrap. Stable across releases.
#
# Two modes:
#   1) run from an unpacked release (server/ next to it) → launch the engine;
#   2) otherwise: download the release tarball, verify its sha256, extract and
#      launch the engine.
#
# Typical usage (any regular user; sudo asks for the password once):
#   curl -fsSL https://github.com/NoTimeToSleep-Team/esp32chat/releases/latest/download/install.sh | sudo bash
#
# Environment:
#   LC_VERSION=x.y.z   install a specific version
#   LC_TARBALL_URL=…   custom tarball URL/path (tests, offline installs)
#   LC_REPO=org/repo   releases repository (default: NoTimeToSleep-Team/esp32chat)
#
# All arguments are passed through to the engine (--no-setup, --preseed …).
set -euo pipefail

LC_REPO="${LC_REPO:-NoTimeToSleep-Team/esp32chat}"

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-}")" 2>/dev/null && pwd)"

log() { echo "[lc] $(date '+%H:%M:%S') $*" >&2; }
die() { echo "[lc] ERROR: $*" >&2; exit 1; }

# Downloads with a few attempts: TLS hiccups ("unexpected eof", connection
# resets) are common on flaky links and are not covered by curl --retry.
download() {
    local url="$1" dest="$2" attempt
    for attempt in 1 2 3; do
        if curl -fsSL --retry 3 --retry-connrefused -o "${dest}" "${url}"; then
            return 0
        fi
        log "download failed (attempt ${attempt}/3): ${url}"
        sleep 3
    done
    return 1
}

command -v curl >/dev/null 2>&1 \
    || die "curl is required to download the release. Install it first: sudo apt-get update && sudo apt-get install -y curl"

# A wrong clock (a fresh Raspberry Pi without an RTC) breaks every HTTPS
# download with a wall of TLS errors — say it up front.
LC_YEAR="$(date +%Y 2>/dev/null || echo 0)"
if (( LC_YEAR < 2024 || LC_YEAR > 2033 )); then
    die "the system clock looks wrong ($(date '+%Y-%m-%d %H:%M')). HTTPS downloads will fail. Set the clock (e.g. 'sudo timedatectl set-ntp true' or 'sudo date -s \"YYYY-MM-DD HH:MM:SS\"') and re-run."
fi

# 0) Running as a regular user? Re-exec through sudo (sudo asks for the
# password once — this is what makes "one command as a random user" work).
if [[ "${EUID}" -ne 0 ]]; then
    if [[ -f "${BASH_SOURCE[0]:-}" && -r "${BASH_SOURCE[0]:-}" ]]; then
        echo "Administrator rights are required — re-running via sudo…"
        exec sudo bash "${BASH_SOURCE[0]}" "$@"
    fi
    die "run as root, e.g.: curl -fsSL <url>/install.sh | sudo bash"
fi

# 1) Unpacked release or repo checkout (engine is right next to us).
if [[ -f "${SELF_DIR}/server/scripts/install_pi.sh" ]]; then
    export SOURCE_ROOT="${SELF_DIR}/server"
    exec bash "${SOURCE_ROOT}/scripts/install_pi.sh" "$@"
fi
if [[ -f "${SELF_DIR}/../scripts/install_pi.sh" ]]; then
    export SOURCE_ROOT="${SELF_DIR}/.."
    exec bash "${SOURCE_ROOT}/scripts/install_pi.sh" "$@"
fi

# 2) Otherwise: download the release tarball, verify and install.

# Resolve the latest release tag without the GitHub API (which is rate-limited
# to 60 requests/hour for anonymous users and is a single point of failure):
# follow the /releases/latest redirect and read the tag from the final URL.
latest_tag_via_redirect() {
    local effective
    effective="$(curl -fsSLI -o /dev/null -w '%{url_effective}' \
        "https://github.com/${LC_REPO}/releases/latest" 2>/dev/null || true)"
    case "${effective}" in
        */tag/v*) printf '%s' "${effective##*/tag/v}" ;;
        *) return 1 ;;
    esac
}

resolve_url() {
    if [[ -n "${LC_TARBALL_URL:-}" ]]; then
        printf '%s' "${LC_TARBALL_URL}"
        return 0
    fi
    local api json url ver
    if [[ -n "${LC_VERSION:-}" ]]; then
        api="https://api.github.com/repos/${LC_REPO}/releases/tags/v${LC_VERSION}"
    else
        api="https://api.github.com/repos/${LC_REPO}/releases/latest"
    fi
    json="$(curl -fsSL --retry 3 "${api}" 2>/dev/null || true)"
    if [[ -z "${json}" ]]; then
        # /latest returns 404 while only pre-releases exist — take the newest release overall
        json="$(curl -fsSL --retry 3 "https://api.github.com/repos/${LC_REPO}/releases?per_page=1" 2>/dev/null || true)"
    fi
    url="$(printf '%s' "${json}" \
        | sed -n 's/.*"browser_download_url": *"\([^"]*lc-server[^"]*\.tar\.gz\)".*/\1/p' \
        | head -1)" || true   # head may SIGPIPE the upstream; pipefail must not kill us

    if [[ -z "${url}" ]]; then
        # The API is rate-limited or down — the releases are still downloadable
        # directly, so resolve the tag via the /releases/latest redirect.
        if [[ -n "${LC_VERSION:-}" ]]; then
            ver="${LC_VERSION}"
        else
            ver="$(latest_tag_via_redirect)" \
                || die "cannot reach GitHub releases for ${LC_REPO}"
        fi
        url="https://github.com/${LC_REPO}/releases/download/v${ver}/lc-server-v${ver}.tar.gz"
        log "GitHub API unavailable — using the direct URL for v${ver}"
    fi
    printf '%s' "${url}"
}

log "downloading the release archive…"
URL="$(resolve_url)"
WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT
TARBALL="${WORK}/$(basename "${URL}")"

download "${URL}" "${TARBALL}" \
    || die "cannot download ${URL}"

if ! download "${URL}.sha256" "${TARBALL}.sha256"; then
    rm -f "${TARBALL}.sha256"
    if [[ "${LC_SKIP_SHA:-0}" == "1" ]]; then
        log "WARNING: sha256 not verified (LC_SKIP_SHA=1)"
    else
        die "cannot download the checksum: ${URL}.sha256"
    fi
else
    ( cd "${WORK}" && sha256sum -c "$(basename "${TARBALL}").sha256" ) >&2 \
        || die "checksum mismatch — the archive is corrupted or was replaced"
    log "sha256 verified"
fi

tar -xzf "${TARBALL}" -C "${WORK}" || die "cannot extract the archive"
PKG="$(tar -tzf "${TARBALL}" | head -1 | cut -d/ -f1)" || true
[[ -n "${PKG}" ]] || die "the archive is empty"

export SOURCE_ROOT="${WORK}/${PKG}/server"
exec bash "${SOURCE_ROOT}/scripts/install_pi.sh" "$@"
