from __future__ import annotations

from typing import Mapping

from firmware.common.protocol import EndpointKind, MessageType, format_idempotency_key, make_envelope
from firmware.common.protocol.models import Envelope

from .config import Esp32ServiceConfig
from .models import HeartbeatStatus, TelemetrySnapshot


class TelemetryEnvelopeFactory:
    def __init__(self, config: Esp32ServiceConfig) -> None:
        self._config = config
        self._counter = 0

    def register_request(self, *, sent_at_ms: int) -> Envelope:
        self._counter += 1
        capabilities = {
            "display": False,
            "keyboard": False,
            "touch": False,
            "storage_profile": "ephemeral",
            "audio_io": False,
            "transports": ["usb_serial", "wifi"],
        }
        return make_envelope(
            message_type=MessageType.DEVICE_REGISTER_REQUEST,
            sender_kind=EndpointKind.DEVICE,
            sender_id=self._config.protocol_sender_id,
            target_kind=EndpointKind.SERVER,
            target_id=self._config.protocol_target_id,
            sent_at_ms=sent_at_ms,
            idempotency_key=format_idempotency_key(
                self._config.protocol_sender_id,
                self._config.boot_id,
                self._counter,
            ),
            payload={
                "device_uid": self._config.device_uid,
                "device_type": "esp32_s3_service",
                "firmware_version": self._config.firmware_version,
                "boot_id": self._config.boot_id,
                "capabilities": capabilities,
            },
        )

    def heartbeat(
        self,
        *,
        sent_at_ms: int,
        uptime_ms: int,
        queue_depth: int,
        status: HeartbeatStatus,
        metrics: Mapping[str, int | float],
    ) -> Envelope:
        return make_envelope(
            message_type=MessageType.DEVICE_HEARTBEAT,
            sender_kind=EndpointKind.DEVICE,
            sender_id=self._config.protocol_sender_id,
            target_kind=EndpointKind.SERVER,
            target_id=self._config.protocol_target_id,
            sent_at_ms=sent_at_ms,
            idempotency_key=None,
            payload={
                "uptime_ms": uptime_ms,
                "queue_depth": queue_depth,
                "status": status.value,
                "metrics": dict(metrics),
            },
        )

    def telemetry_snapshot(self, *, sent_at_ms: int, snapshot: TelemetrySnapshot) -> Envelope:
        return make_envelope(
            message_type=MessageType.TELEMETRY_SNAPSHOT,
            sender_kind=EndpointKind.DEVICE,
            sender_id=self._config.protocol_sender_id,
            target_kind=EndpointKind.SERVER,
            target_id=self._config.protocol_target_id,
            sent_at_ms=sent_at_ms,
            idempotency_key=None,
            payload=snapshot.to_payload(),
        )
