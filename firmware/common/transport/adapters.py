from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ..protocol.codec import make_envelope
from ..protocol.constants import EndpointKind, MessageType
from ..protocol.models import Envelope
from .errors import TransportIOError


class TransportAdapter(Protocol):
    def send(self, envelope: Envelope) -> Envelope:
        ...


@dataclass(frozen=True)
class SentFrame:
    message_id: str
    message_type: str


class InMemoryTransportAdapter:
    def __init__(self, handler: Callable[[Envelope], Envelope] | None = None) -> None:
        self._handler = handler
        self._sent_frames: list[SentFrame] = []

    @property
    def sent_frames(self) -> tuple[SentFrame, ...]:
        return tuple(self._sent_frames)

    def send(self, envelope: Envelope) -> Envelope:
        self._sent_frames.append(
            SentFrame(message_id=envelope.message_id, message_type=envelope.message_type)
        )

        if self._handler is not None:
            return self._handler(envelope)

        return self._default_handler(envelope)

    @staticmethod
    def _default_handler(envelope: Envelope) -> Envelope:
        message_type = MessageType(envelope.message_type)

        if message_type == MessageType.SYNC_PUSH_REQUEST:
            events = envelope.payload.get("events", [])
            if not isinstance(events, list):
                raise TransportIOError("payload.events must be an array")

            applied_event_ids = []
            for event in events:
                if isinstance(event, dict) and isinstance(event.get("event_id"), str):
                    applied_event_ids.append(event["event_id"])

            payload = {
                "status": "ok",
                "applied_event_ids": applied_event_ids,
                "duplicate_event_ids": [],
                "rejected": [],
                "next_cursor": envelope.payload.get("base_cursor", "cur-0"),
                "server_time_ms": envelope.sent_at_ms + 1,
            }
            return make_envelope(
                message_type=MessageType.SYNC_PUSH_RESPONSE,
                sender_kind=EndpointKind.SERVER,
                sender_id=envelope.target.endpoint_id,
                target_kind=EndpointKind.DEVICE,
                target_id=envelope.sender.endpoint_id,
                sent_at_ms=envelope.sent_at_ms + 1,
                correlation_id=envelope.message_id,
                payload=payload,
            )

        if message_type == MessageType.SYNC_PULL_REQUEST:
            payload = {
                "status": "ok",
                "events": [],
                "next_cursor": envelope.payload.get("since_cursor", "cur-0"),
                "has_more": False,
                "server_time_ms": envelope.sent_at_ms + 1,
            }
            return make_envelope(
                message_type=MessageType.SYNC_PULL_RESPONSE,
                sender_kind=EndpointKind.SERVER,
                sender_id=envelope.target.endpoint_id,
                target_kind=EndpointKind.DEVICE,
                target_id=envelope.sender.endpoint_id,
                sent_at_ms=envelope.sent_at_ms + 1,
                correlation_id=envelope.message_id,
                payload=payload,
            )

        if message_type == MessageType.SYNC_ACK:
            return make_envelope(
                message_type=MessageType.SYNC_ACK,
                sender_kind=EndpointKind.SERVER,
                sender_id=envelope.target.endpoint_id,
                target_kind=EndpointKind.DEVICE,
                target_id=envelope.sender.endpoint_id,
                sent_at_ms=envelope.sent_at_ms + 1,
                correlation_id=envelope.message_id,
                payload={
                    "applied_cursor": envelope.payload.get("applied_cursor", "cur-0"),
                    "received_event_ids": envelope.payload.get("received_event_ids", []),
                },
            )

        return make_envelope(
            message_type=MessageType.ERROR_RESPONSE,
            sender_kind=EndpointKind.SERVER,
            sender_id=envelope.target.endpoint_id,
            target_kind=EndpointKind.DEVICE,
            target_id=envelope.sender.endpoint_id,
            sent_at_ms=envelope.sent_at_ms + 1,
            correlation_id=envelope.message_id,
            payload={
                "error": {
                    "code": "unsupported_message_type",
                    "message": f"Unsupported message type: {envelope.message_type}",
                    "retryable": False,
                },
                "server_time_ms": envelope.sent_at_ms + 1,
            },
        )
