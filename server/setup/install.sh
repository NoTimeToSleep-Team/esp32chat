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

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"

log() { echo "[lc] $(date '+%H:%M:%S') $*" >&2; }
die() { echo "[lc] ERROR: $*" >&2; exit 1; }

# 0) Running as a regular user? Re-exec through sudo (sudo asks for the
# password once — this is what makes "one command as a random user" work).
if [[ "${EUID}" -ne 0 ]]; then
    if [[ -f "${BASH_SOURCE[0]}" && -r "${BASH_SOURCE[0]}" ]]; then
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

resolve_url() {
    if [[ -n "${LC_TARBALL_URL:-}" ]]; then
        printf '%s' "${LC_TARBALL_URL}"
        return 0
    fi
    local api json url
    if [[ -n "${LC_VERSION:-}" ]]; then
        api="https://api.github.com/repos/${LC_REPO}/releases/tags/v${LC_VERSION}"
    else
        api="https://api.github.com/repos/${LC_REPO}/releases/latest"
    fi
    json="$(curl -fsSL --retry 3 "${api}" 2>/dev/null || true)"
    if [[ -z "${json}" ]]; then
        # /latest returns 404 while only pre-releases exist — take the newest release overall
        json="$(curl -fsSL --retry 3 "https://api.github.com/repos/${LC_REPO}/releases?per_page=1")" \
            || die "cannot reach GitHub releases for ${LC_REPO}"
    fi
    url="$(printf '%s' "${json}" \
        | sed -n 's/.*"browser_download_url": *"\([^"]*lc-server[^"]*\.tar\.gz\)".*/\1/p' \
        | head -1)" || true   # head may SIGPIPE the upstream; pipefail must not kill us
    [[ -n "${url}" ]] || die "no lc-server-*.tar.gz asset found in the release"
    printf '%s' "${url}"
}

log "downloading the release archive…"
URL="$(resolve_url)"
WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT
TARBALL="${WORK}/$(basename "${URL}")"

curl -fsSL --retry 3 -o "${TARBALL}" "${URL}" \
    || die "cannot download ${URL}"

if ! curl -fsSL --retry 3 -o "${TARBALL}.sha256" "${URL}.sha256"; then
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
