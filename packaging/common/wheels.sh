#!/usr/bin/env bash
# Build the application wheel and download every dependency wheel for the
# supported CPython versions and platforms into one flat directory.
#
# The packages bundle this directory: at install time pip runs offline
# (--no-index --find-links) and picks the wheels that match the host
# interpreter. This is what makes a single .deb work on Debian 12 (3.11),
# Debian 13 (3.13), Ubuntu 22.04 (3.10) and Ubuntu 24.04 (3.12).
#
# Usage:
#   wheels.sh OUT_DIR ["3.10 3.11 3.12 3.13"] \
#                     ["manylinux2014_x86_64 manylinux2014_aarch64"]
set -euo pipefail

OUT="${1:?usage: wheels.sh OUT_DIR [PYVERS] [PLATFORMS]}"
PYVERS="${2:-3.10 3.11 3.12 3.13 3.14}"
PLATFORMS="${3:-manylinux2014_x86_64 manylinux2014_aarch64}"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${HERE}/../.." && pwd)"
SERVER="${REPO_ROOT}/server"

log() { echo "[wheels] $*" >&2; }

mkdir -p "${OUT}"
WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

# Isolated build tooling (avoids PEP 668 "externally managed" on Debian/Ubuntu)
log "preparing the build environment"
python3 -m venv "${WORK}/tool"
"${WORK}/tool/bin/python" -m pip install --quiet --disable-pip-version-check --upgrade pip build

log "building the application wheel"
"${WORK}/tool/bin/python" -m build --wheel --outdir "${WORK}/app" "${SERVER}" >/dev/null
cp "${WORK}/app/"*.whl "${OUT}/"

# Dependency list: pyproject.toml is the single source of truth
python3 - "${SERVER}/pyproject.toml" > "${WORK}/requirements.txt" <<'PY'
import sys
import tomllib

with open(sys.argv[1], "rb") as fh:
    project = tomllib.load(fh)["project"]
for dependency in project["dependencies"]:
    print(dependency)
PY

for platform in ${PLATFORMS}; do
    for py in ${PYVERS}; do
        abi="cp${py//./}"
        log "downloading ${abi} wheels for ${platform}"
        "${WORK}/tool/bin/python" -m pip download \
            --quiet --disable-pip-version-check \
            --only-binary=:all: \
            --python-version "${py}" \
            --platform "${platform}" \
            --implementation cp \
            --abi "${abi}" \
            --dest "${WORK}/download/${platform}/${py}" \
            -r "${WORK}/requirements.txt"
    done
done

# pip evaluates environment markers of transitive dependencies against the
# *running* interpreter even when --python-version is set, so packages gated
# by e.g. `python_version < "3.11"` are not discovered during cross-download.
# Fetch the known marker-gated extras explicitly (pure-python wheels). The
# install-time test matrix on Debian 12/13 and Ubuntu 22.04/24.04 verifies
# that the bundle is complete for every supported interpreter.
LEGACY_EXTRAS="exceptiongroup>=1.0.2 sniffio>=1.1"
log "downloading legacy marker extras"
"${WORK}/tool/bin/python" -m pip download \
    --quiet --disable-pip-version-check \
    --only-binary=:all: \
    --dest "${WORK}/legacy" \
    ${LEGACY_EXTRAS}

# Flat directory: identical py3-none-any wheels are shared between the sets
find "${WORK}/download" "${WORK}/legacy" -name '*.whl' -print0 \
    | while IFS= read -r -d '' wheel; do cp -n "${wheel}" "${OUT}/"; done

log "done: $(find "${OUT}" -maxdepth 1 -name '*.whl' | wc -l) wheels, $(du -sh "${OUT}" | cut -f1) in ${OUT}"
