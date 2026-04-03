from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class M5TabConfig:
    device_uid: str = "m5tab-01"
    firmware_version: str = "0.9.1"
    server_base_url: str = "http://127.0.0.1:8000"
    info_refresh_interval_ms: int = 5000
