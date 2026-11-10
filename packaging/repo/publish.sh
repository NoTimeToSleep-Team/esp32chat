#!/usr/bin/env bash
# Assemble the signed package repository tree from built packages.
#
# Usage (environment):
#   DIST_DIR   directory with built packages (deb/rpm/pkg.tar.zst + release rpm)
#   REPO_DIR   output repository tree (may contain a previous run — new
#              packages are added, old versions pruned, metadata regenerated)
#   VERSION    release version (0.1.10)
#   KEEP       how many recent versions to keep in the repo (default 3)
#   GPG_KEY    signing key id/fingerprint; empty = unsigned (local tests)
#   GPG_PASSPHRASE  passphrase for the signing key (optional)
#   BASE_URL   public repository URL (for the bootstrap scripts)
set -euo pipefail

DIST_DIR="${DIST_DIR:?set DIST_DIR}"
REPO_DIR="${REPO_DIR:?set REPO_DIR}"
VERSION="${VERSION:?set VERSION}"
KEEP="${KEEP:-3}"
GPG_KEY="${GPG_KEY:-}"
GPG_PASSPHRASE="${GPG_PASSPHRASE:-}"
BASE_URL="${BASE_URL:-https://notimetosleep-team.github.io/esp32chat}"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
log() { echo "[repo] $*" >&2; }

gpg_run() {
    local args=(--batch --yes)
    if [ -n "${GPG_PASSPHRASE}" ]; then
        args+=(--pinentry-mode loopback --passphrase "${GPG_PASSPHRASE}")
    fi
    gpg "${args[@]}" "$@"
}

APT_POOL="${REPO_DIR}/apt/pool/main/l/local-chat"
APT_DISTS="${REPO_DIR}/apt/dists/stable"
RPM_DIR="${REPO_DIR}/rpm"
ARCH_DIR="${REPO_DIR}/arch/x86_64"
mkdir -p "${APT_POOL}" "${RPM_DIR}" "${ARCH_DIR}" \
    "${APT_DISTS}/main/binary-amd64" "${APT_DISTS}/main/binary-arm64"

# ---- public key (needed by the release rpm too) ---------------------------
if [ -n "${GPG_KEY}" ]; then
    gpg_run --armor --export "${GPG_KEY}" > "${REPO_DIR}/local-chat.gpg"
fi

# ---- release rpm (repo definition + key import) ---------------------------
if [ -n "${GPG_KEY}" ] && command -v rpmbuild >/dev/null 2>&1; then
    log "building the release rpm"
    BASE_URL="${BASE_URL}" KEY_FILE="${REPO_DIR}/local-chat.gpg" OUT_DIR="${DIST_DIR}" \
        bash "${HERE}/build-release-rpm.sh"
else
    log "release rpm not rebuilt (no key or no rpmbuild)"
fi

# ---- collect packages ------------------------------------------------------
log "collecting packages from ${DIST_DIR}"
cp -f "${DIST_DIR}"/local-chat_*.deb "${APT_POOL}/" 2>/dev/null || true
cp -f "${DIST_DIR}"/local-chat-*.rpm "${RPM_DIR}/" 2>/dev/null || true
cp -f "${DIST_DIR}"/local-chat-*.pkg.tar.zst "${ARCH_DIR}/" 2>/dev/null || true

# ---- prune old versions (keep the newest KEEP) -----------------------------
python3 "${HERE}/prune.py" "${APT_POOL}" --ext deb --keep "${KEEP}" || true
python3 "${HERE}/prune.py" "${RPM_DIR}" --ext rpm --keep "${KEEP}" || true
python3 "${HERE}/prune.py" "${ARCH_DIR}" --ext pkg --keep "${KEEP}" || true

# ---- apt metadata ----------------------------------------------------------
if ls "${APT_POOL}"/*.deb >/dev/null 2>&1; then
    log "generating apt metadata"
    TMP_PACKAGES="$(mktemp)"
    (
        cd "${REPO_DIR}/apt"
        apt-ftparchive packages pool > "${TMP_PACKAGES}"
    )
    python3 "${HERE}/split_packages.py" "${TMP_PACKAGES}" "${APT_DISTS}/main" >/dev/null
    rm -f "${TMP_PACKAGES}"
    for arch in amd64 arm64; do
        out="${APT_DISTS}/main/binary-${arch}"
        mkdir -p "${out}"
        src="${APT_DISTS}/main/Packages-${arch}"
        if [ -f "${src}" ]; then
            mv "${src}" "${out}/Packages"
        else
            : > "${out}/Packages"
        fi
        gzip -9kf "${out}/Packages"
    done
    rm -f "${APT_DISTS}/Release" "${APT_DISTS}/Release.gpg" "${APT_DISTS}/InRelease"
    (
        cd "${REPO_DIR}/apt"
        apt-ftparchive \
            -o APT::FTPArchive::Release::Origin="Local Chat" \
            -o APT::FTPArchive::Release::Label="Local Chat" \
            -o APT::FTPArchive::Release::Suite="stable" \
            -o APT::FTPArchive::Release::Codename="stable" \
            -o APT::FTPArchive::Release::Architectures="amd64 arm64" \
            -o APT::FTPArchive::Release::Components="main" \
            -o APT::FTPArchive::Release::Description="Local Chat package repository" \
            release dists/stable > dists/stable/Release
    )
    if [ -n "${GPG_KEY}" ]; then
        log "signing the apt metadata"
        gpg_run --local-user "${GPG_KEY}" --armor --detach-sign \
            -o "${APT_DISTS}/Release.gpg" "${APT_DISTS}/Release"
        gpg_run --local-user "${GPG_KEY}" --clearsign \
            -o "${APT_DISTS}/InRelease" "${APT_DISTS}/Release"
    fi
else
    log "no .deb packages — apt metadata skipped"
fi

# ---- rpm metadata ----------------------------------------------------------
if ls "${RPM_DIR}"/local-chat-[0-9]*.rpm >/dev/null 2>&1; then
    if [ -n "${GPG_KEY}" ] && command -v rpmsign >/dev/null 2>&1; then
        log "signing rpm packages"
        cat > "${HOME}/.rpmmacros" <<EOF
%_gpg_name ${GPG_KEY}
%__gpg_sign_cmd %{__gpg} gpg --batch --yes --pinentry-mode loopback --passphrase ${GPG_PASSPHRASE:-} --no-verbose --no-armor --no-secmem-warning -u "%{_gpg_name}" -sbo %{__signature_filename} %{__plaintext_filename}
EOF
        rpmsign --addsign "${RPM_DIR}"/local-chat-[0-9]*.rpm
    fi
    log "generating rpm metadata"
    createrepo_c --quiet --database "${RPM_DIR}"
    if [ -n "${GPG_KEY}" ]; then
        log "signing rpm metadata"
        gpg_run --local-user "${GPG_KEY}" --armor --detach-sign \
            -o "${RPM_DIR}/repodata/repomd.xml.asc" "${RPM_DIR}/repodata/repomd.xml"
    fi
else
    log "no .rpm packages — rpm metadata skipped"
fi

# ---- pacman metadata -------------------------------------------------------
if ls "${ARCH_DIR}"/*.pkg.tar.zst >/dev/null 2>&1; then
    log "generating pacman metadata"
    python3 "${HERE}/make_pacman_db.py" "${ARCH_DIR}" >/dev/null
    if [ -n "${GPG_KEY}" ]; then
        log "signing pacman metadata"
        gpg_run --local-user "${GPG_KEY}" --detach-sign \
            -o "${ARCH_DIR}/localchat.db.tar.gz.sig" "${ARCH_DIR}/localchat.db.tar.gz"
    fi
else
    log "no pacman packages — pacman metadata skipped"
fi

# ---- public key + bootstrap files -----------------------------------------
install -m 0755 "${HERE}/setup-apt.sh" "${REPO_DIR}/setup-apt.sh"
install -m 0755 "${HERE}/setup-arch.sh" "${REPO_DIR}/setup-arch.sh"
install -m 0644 "${HERE}/local-chat.repo.in" "${REPO_DIR}/local-chat.repo"
sed -i "s|@BASE_URL@|${BASE_URL}|g" "${REPO_DIR}/local-chat.repo"
install -m 0644 "${HERE}/index.html" "${REPO_DIR}/index.html"

log "repository ready in ${REPO_DIR}"
