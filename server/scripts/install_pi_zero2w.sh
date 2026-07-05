#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export DEFAULT_ENV_TEMPLATE="${DEFAULT_ENV_TEMPLATE:-pi-zero2w.env.example}"

exec bash "${SCRIPT_DIR}/install_pi.sh"
