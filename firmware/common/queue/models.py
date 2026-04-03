from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .states import QueueEventState


@dataclass
class QueueEventRecord:
    event_id: str
    event_type: str
    event_ts_ms: int
    idempotency_key: str
    payload_hash: str
    payload: dict[str, Any]
    state: QueueEventState = QueueEventState.PENDING
    retry_count: int = 0
    last_attempt_ms: int | None = None
    acked_at_ms: int | None = None
    last_error: str | None = None
