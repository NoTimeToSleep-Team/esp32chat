#!/usr/bin/env bash
# LC v0.1 — shared installer library.
# Lives at server/setup/lib.sh (in the repo and in the installed tree).
# Sourced by: scripts/lc.sh (through ${APP_ROOT}/setup/lib.sh).

LC_REPO="${LC_REPO:-NoTimeToSleep-Team/esp32chat}"

lc_log() {
    # IMPORTANT: to stderr — stdout of the fetch helpers carries the result
    # (the package path) captured by the caller.
    echo "[lc] $(date '+%H:%M:%S') $*" >&2
}

lc_fail() {
    lc_log "ERROR: $*" >&2
    exit 1
}

# The system clock must be roughly right: HTTPS downloads fail with a wall of
# TLS errors on a fresh Raspberry Pi that has no RTC yet.
lc_clock_check() {
    local year
    year="$(date +%Y 2>/dev/null || echo 0)"
    if (( year < 2024 || year > 2033 )); then
        lc_fail "the system clock looks wrong ($(date '+%Y-%m-%d %H:%M')). HTTPS downloads will fail. Set the clock (e.g. 'sudo timedatectl set-ntp true' or 'sudo date -s \"YYYY-MM-DD HH:MM:SS\"') and re-run."
    fi
}

# Resolve the latest release tag without the GitHub API (rate-limited to
# 60 requests/hour for anonymous users): follow the /releases/latest redirect
# and read the tag from the final URL.
lc_latest_tag_via_redirect() {
    local effective
    effective="$(curl -fsSLI -o /dev/null -w '%{url_effective}' \
        "https://github.com/${LC_REPO}/releases/latest" 2>/dev/null || true)"
    case "${effective}" in
        */tag/v*) printf '%s' "${effective##*/tag/v}" ;;
        *) return 1 ;;
    esac
}

# Prints the release tarball URL:
#   1) LC_TARBALL_URL (URL or local path, file:// included);
#   2) a specific version LC_VERSION -> releases/tags/v<version>;
#   3) the latest GitHub release (falls back to the newest release overall
#      when only pre-releases exist, and to the direct download URL when the
#      GitHub API itself is rate-limited or unreachable).
lc_release_url() {
    if [[ -n "${LC_TARBALL_URL:-}" ]]; then
        printf '%s' "${LC_TARBALL_URL}"
        return 0
    fi

    local api_url
    if [[ -n "${LC_VERSION:-}" ]]; then
        api_url="https://api.github.com/repos/${LC_REPO}/releases/tags/v${LC_VERSION}"
    else
        api_url="https://api.github.com/repos/${LC_REPO}/releases/latest"
    fi

    local json url ver
    json="$(curl -fsSL --retry 3 "${api_url}" 2>/dev/null || true)"
    if [[ -z "${json}" ]]; then
        json="$(curl -fsSL --retry 3 "https://api.github.com/repos/${LC_REPO}/releases?per_page=1" 2>/dev/null || true)"
    fi
    url="$(printf '%s' "${json}" \
        | sed -n 's/.*"browser_download_url": *"\([^"]*lc-server[^"]*\.tar\.gz\)".*/\1/p' \
        | head -1)" || true   # head may SIGPIPE the upstream; pipefail must not kill us

    if [[ -z "${url}" ]]; then
        if [[ -n "${LC_VERSION:-}" ]]; then
            ver="${LC_VERSION}"
        else
            ver="$(lc_latest_tag_via_redirect)" \
                || lc_fail "cannot reach GitHub releases for ${LC_REPO}"
        fi
        url="https://github.com/${LC_REPO}/releases/download/v${ver}/lc-server-v${ver}.tar.gz"
        lc_log "GitHub API unavailable — using the direct URL for v${ver}"
    fi
    printf '%s' "${url}"
}

# Downloads with a few attempts: TLS hiccups ("unexpected eof", connection
# resets) are common on flaky links and are not covered by curl --retry.
lc_download() {
    local url="$1" dest="$2" attempt
    for attempt in 1 2 3; do
        if curl -fsSL --retry 3 --retry-connrefused -o "${dest}" "${url}"; then
            return 0
        fi
        lc_log "download failed (attempt ${attempt}/3): ${url}"
        sleep 3
    done
    return 1
}

# Downloads the tarball + its .sha256, verifies, extracts into $1 and prints
# the package root directory.
lc_fetch_release() {
    local dest_dir="$1"
    local url sha_url tarball pkg_root

    lc_clock_check
    url="$(lc_release_url)"
    sha_url="${url}.sha256"
    tarball="${dest_dir}/$(basename "${url}")"
    mkdir -p "${dest_dir}"

    lc_log "downloading ${url}"
    lc_download "${url}" "${tarball}" \
        || lc_fail "cannot download the tarball: ${url}"

    if ! lc_download "${sha_url}" "${tarball}.sha256"; then
        rm -f "${tarball}.sha256"
        if [[ "${LC_SKIP_SHA:-0}" == "1" ]]; then
            lc_log "WARNING: sha256 not verified (file unavailable, LC_SKIP_SHA=1)"
        else
            lc_fail "cannot download the checksum: ${sha_url}"
        fi
    else
        ( cd "${dest_dir}" && sha256sum -c "$(basename "${tarball}").sha256" ) >&2 \
            || lc_fail "checksum mismatch — the archive is corrupted or was replaced"
        lc_log "sha256 verified"
    fi

    tar -xzf "${tarball}" -C "${dest_dir}" \
        || lc_fail "cannot extract the archive"
    pkg_root="$(tar -tzf "${tarball}" | head -1 | cut -d/ -f1)" || true
    [[ -n "${pkg_root}" ]] || lc_fail "the archive is empty"
    rm -f "${tarball}" "${tarball}.sha256"
    printf '%s' "${dest_dir}/${pkg_root}"
}
