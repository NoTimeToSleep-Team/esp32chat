from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceNodeRecord:
    device_id: str
    device_type: str
    status: str
    last_seen_ms: int | None
    metadata: dict[str, object]
