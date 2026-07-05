from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class M5StampConfig:
    device_uid: str = "m5stamp-s3-01"
    firmware_version: str = "0.8.2"
    protocol_sender_id: str = "m5stamp-s3-01"
    protocol_target_id: str = "main"
    boot_id: str = "boot-default"
    server_base_url: str = "http://127.0.0.1:8000"
    heartbeat_interval_ms: int = 15000
    telemetry_interval_ms: int = 45000
