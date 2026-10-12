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

# Prints the release tarball URL:
#   1) LC_TARBALL_URL (URL or local path, file:// included);
#   2) a specific version LC_VERSION -> releases/tags/v<version>;
#   3) the latest GitHub release (falls back to the newest release overall
#      when only pre-releases exist).
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

    local json url
    json="$(curl -fsSL --retry 3 "${api_url}" 2>/dev/null || true)"
    if [[ -z "${json}" ]]; then
        json="$(curl -fsSL --retry 3 "https://api.github.com/repos/${LC_REPO}/releases?per_page=1")" \
            || lc_fail "cannot reach GitHub releases for ${LC_REPO}"
    fi
    url="$(printf '%s' "${json}" \
        | sed -n 's/.*"browser_download_url": *"\([^"]*lc-server[^"]*\.tar\.gz\)".*/\1/p' \
        | head -1)" || true   # head may SIGPIPE the upstream; pipefail must not kill us
    [[ -n "${url}" ]] || lc_fail "no lc-server-*.tar.gz asset found in the release"
    printf '%s' "${url}"
}

# Downloads the tarball + its .sha256, verifies, extracts into $1 and prints
# the package root directory.
lc_fetch_release() {
    local dest_dir="$1"
    local url sha_url tarball pkg_root

    url="$(lc_release_url)"
    sha_url="${url}.sha256"
    tarball="${dest_dir}/$(basename "${url}")"
    mkdir -p "${dest_dir}"

    lc_log "downloading ${url}"
    curl -fsSL --retry 3 -o "${tarball}" "${url}" \
        || lc_fail "cannot download the tarball: ${url}"

    if ! curl -fsSL --retry 3 -o "${tarball}.sha256" "${sha_url}"; then
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
