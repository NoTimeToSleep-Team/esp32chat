from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Endpoint:
    kind: str
    endpoint_id: str

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "id": self.endpoint_id,
        }


@dataclass(frozen=True)
class Envelope:
    protocol_version: str
    message_type: str
    message_id: str
    idempotency_key: str | None
    correlation_id: str | None
    sender: Endpoint
    target: Endpoint
    sent_at_ms: int
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_version": self.protocol_version,
            "message_type": self.message_type,
            "message_id": self.message_id,
            "idempotency_key": self.idempotency_key,
            "correlation_id": self.correlation_id,
            "sender": self.sender.to_dict(),
            "target": self.target.to_dict(),
            "sent_at_ms": self.sent_at_ms,
            "payload": self.payload,
        }
