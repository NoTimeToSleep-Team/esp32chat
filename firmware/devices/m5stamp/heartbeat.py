from __future__ import annotations

from typing import Any

from firmware.common.protocol import EndpointKind, MessageType, make_envelope
from firmware.common.protocol.models import Envelope

from .config import M5StampConfig
from .models import HeartbeatStatus, IndicatorState, TelemetrySnapshotData


class M5StampEnvelopeFactory:
    def __init__(self, config: M5StampConfig) -> None:
        self._config = config

    def heartbeat(
        self,
        *,
        now_ms: int,
        uptime_ms: int,
        queue_depth: int,
        status: HeartbeatStatus,
        indicator_state: IndicatorState,
        active_signals: tuple[str, ...],
        network_ok: bool,
    ) -> Envelope:
        payload = {
            "uptime_ms": uptime_ms,
            "queue_depth": queue_depth,
            "status": status.value,
            "metrics": {
                "network_ok": network_ok,
                "active_signal_count": len(active_signals),
                "indicator_pattern": indicator_state.pattern.value,
                "indicator_brightness_pct": indicator_state.brightness_pct,
            },
        }
        return make_envelope(
            message_type=MessageType.DEVICE_HEARTBEAT,
            sender_kind=EndpointKind.DEVICE,
            sender_id=self._config.protocol_sender_id,
            target_kind=EndpointKind.SERVER,
            target_id=self._config.protocol_target_id,
            sent_at_ms=now_ms,
            idempotency_key=None,
            payload=payload,
        )

    def telemetry_snapshot(
        self,
        *,
        now_ms: int,
        snapshot_data: TelemetrySnapshotData,
        active_signals: tuple[str, ...],
    ) -> Envelope:
        payload = snapshot_data.to_payload()
        service_flags = payload.get("service_flags")
        if isinstance(service_flags, dict):
            service_flags["active_signals"] = list(active_signals)

        return make_envelope(
            message_type=MessageType.TELEMETRY_SNAPSHOT,
            sender_kind=EndpointKind.DEVICE,
            sender_id=self._config.protocol_sender_id,
            target_kind=EndpointKind.SERVER,
            target_id=self._config.protocol_target_id,
            sent_at_ms=now_ms,
            idempotency_key=None,
            payload=payload,
        )

    def register_request(self, *, now_ms: int) -> Envelope:
        payload: dict[str, Any] = {
            "device_uid": self._config.device_uid,
            "device_type": "m5stamp_s3_internal_node",
            "firmware_version": self._config.firmware_version,
            "boot_id": self._config.boot_id,
            "capabilities": {
                "display": False,
                "keyboard": False,
                "touch": False,
                "storage_profile": "ephemeral",
                "audio_io": False,
                "transports": ["usb_serial", "wifi"],
                "heartbeat": True,
                "alert_signal": True,
            },
        }
        return make_envelope(
            message_type=MessageType.DEVICE_REGISTER_REQUEST,
            sender_kind=EndpointKind.DEVICE,
            sender_id=self._config.protocol_sender_id,
            target_kind=EndpointKind.SERVER,
            target_id=self._config.protocol_target_id,
            sent_at_ms=now_ms,
            idempotency_key=f"{self._config.protocol_sender_id}:{self._config.boot_id}:000001",
            payload=payload,
        )
