from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DevicePairRequest:
    pairing_id: str
    device_id: str
    device_type: str
    name: str
    code: str
    created_at_ms: int
    expires_at_ms: int
    status: str


@dataclass(frozen=True)
class PairedDevice:
    device_id: str
    device_type: str
    name: str
    paired_at_ms: int
