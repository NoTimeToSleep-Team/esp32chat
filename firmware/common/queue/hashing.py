from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


def payload_hash(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    digest = hashlib.sha256(canonical.encode("ascii")).hexdigest()
    return f"sha256:{digest}"
