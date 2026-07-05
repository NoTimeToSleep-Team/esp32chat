from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FlipperZeroConfig:
    profile_id: str = "flipper_zero"
    base_url: str = "http://127.0.0.1:8000"
    request_timeout_s: float = 5.0
    client_kind: str = "device"
