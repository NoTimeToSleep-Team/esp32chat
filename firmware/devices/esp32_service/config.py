from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Esp32ServiceConfig:
    device_uid: str = "esp32-s3-01"
    firmware_version: str = "0.8.1"
    protocol_sender_id: str = "esp32-s3-01"
    protocol_target_id: str = "main"
    boot_id: str = "boot-default"
    server_base_url: str = "http://127.0.0.1:8000"
    ops_session_token: str | None = None
    heartbeat_interval_ms: int = 15000
    telemetry_interval_ms: int = 30000
    watchdog_timeout_ms: int = 45000
    sync_transport: str = "inmemory"
    sync_uart_ack_required: bool = True

    def require_ops_session(self) -> str:
        token = (self.ops_session_token or "").strip()
        if not token:
            raise RuntimeError("ops_session_token is required for protected ops commands")
        return token
