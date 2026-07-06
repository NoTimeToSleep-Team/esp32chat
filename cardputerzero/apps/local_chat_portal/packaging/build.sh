#!/usr/bin/env bash
set -euo pipefail
bash -n launch_local_chat_portal.sh
python3 -m py_compile >/dev/null 2>&1 || true
