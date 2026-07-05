#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export DEFAULT_ENV_TEMPLATE="${DEFAULT_ENV_TEMPLATE:-cardputerzero.env.example}"

exec bash "${SCRIPT_DIR}/install_pi.sh"
