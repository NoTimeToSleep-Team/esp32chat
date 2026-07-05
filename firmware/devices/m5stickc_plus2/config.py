from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class M5StickCPlus2Config:
    profile_id: str = "m5stickc_plus2"
    base_url: str = "http://127.0.0.1:8000"
    request_timeout_s: float = 5.0
    client_kind: str = "device"
