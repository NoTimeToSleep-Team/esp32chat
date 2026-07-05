from __future__ import annotations

import uuid
from typing import Any, Mapping, Protocol

from .hashing import payload_hash
from .models import QueueEventRecord
from .states import QueueEventState


class QueueValidationError(RuntimeError):
    pass


class RetryGate(Protocol):
    def can_attempt(self, *, retry_count: int, last_attempt_ms: int | None, now_ms: int) -> bool:
        ...


class LocalEventQueue:
    def __init__(self) -> None:
        self._events: dict[str, QueueEventRecord] = {}
        self._order: list[str] = []
        self._idempotency_index: dict[str, str] = {}

    def enqueue(
        self,
        *,
        event_type: str,
        event_ts_ms: int,
        idempotency_key: str,
        payload: Mapping[str, Any],
        event_id: str | None = None,
    ) -> QueueEventRecord:
        normalized_event_type = event_type.strip()
        normalized_idempotency = idempotency_key.strip()
        if not normalized_event_type:
            raise QueueValidationError("event_type must not be empty")
        if not normalized_idempotency:
            raise QueueValidationError("idempotency_key must not be empty")
        if event_ts_ms < 0:
            raise QueueValidationError("event_ts_ms must be >= 0")

        normalized_event_id = (event_id or f"evt-{uuid.uuid4().hex}").strip()
        if not normalized_event_id:
            raise QueueValidationError("event_id must not be empty")

        payload_dict = dict(payload)
        computed_hash = payload_hash(payload_dict)

        duplicate_event_id = self._idempotency_index.get(normalized_idempotency)
        if duplicate_event_id is not None:
            existing = self._events[duplicate_event_id]
            if existing.payload_hash != computed_hash or existing.event_type != normalized_event_type:
                raise QueueValidationError(
                    "idempotency_key is already used for different payload or event_type"
                )
            return existing

        if normalized_event_id in self._events:
            raise QueueValidationError(f"event_id already exists: {normalized_event_id}")

        event = QueueEventRecord(
            event_id=normalized_event_id,
            event_type=normalized_event_type,
            event_ts_ms=event_ts_ms,
            idempotency_key=normalized_idempotency,
            payload_hash=computed_hash,
            payload=payload_dict,
        )
        self._events[event.event_id] = event
        self._order.append(event.event_id)
        self._idempotency_index[event.idempotency_key] = event.event_id
        return event

    def get(self, event_id: str) -> QueueEventRecord:
        if event_id not in self._events:
            raise QueueValidationError(f"unknown event_id: {event_id}")
        return self._events[event_id]

    def all_events(self) -> list[QueueEventRecord]:
        return [self._events[event_id] for event_id in self._order]

    def get_retry_ready(
        self,
        *,
        now_ms: int,
        retry_gate: RetryGate,
        limit: int,
    ) -> list[QueueEventRecord]:
        if limit <= 0:
            return []

        selected: list[QueueEventRecord] = []
        for event_id in self._order:
            event = self._events[event_id]
            if event.state not in {QueueEventState.PENDING, QueueEventState.SENT}:
                continue
            if retry_gate.can_attempt(
                retry_count=event.retry_count,
                last_attempt_ms=event.last_attempt_ms,
                now_ms=now_ms,
            ):
                selected.append(event)
                if len(selected) >= limit:
                    break
        return selected

    def mark_sent(self, *, event_id: str, attempt_ms: int) -> QueueEventRecord:
        event = self.get(event_id)
        if event.state in {
            QueueEventState.ACKED,
            QueueEventState.DUPLICATE,
            QueueEventState.REJECTED,
        }:
            return event

        event.state = QueueEventState.SENT
        event.retry_count += 1
        event.last_attempt_ms = attempt_ms
        return event

    def mark_retryable(self, *, event_id: str, at_ms: int, error: str | None = None) -> QueueEventRecord:
        event = self.get(event_id)
        if event.state in {
            QueueEventState.ACKED,
            QueueEventState.DUPLICATE,
            QueueEventState.REJECTED,
        }:
            return event

        event.state = QueueEventState.PENDING
        event.last_attempt_ms = at_ms
        event.last_error = (error or "").strip() or None
        return event

    def mark_acked(self, *, event_id: str, acked_at_ms: int) -> QueueEventRecord:
        event = self.get(event_id)
        event.state = QueueEventState.ACKED
        event.acked_at_ms = acked_at_ms
        event.last_error = None
        return event

    def mark_duplicate(self, *, event_id: str, acked_at_ms: int) -> QueueEventRecord:
        event = self.get(event_id)
        event.state = QueueEventState.DUPLICATE
        event.acked_at_ms = acked_at_ms
        event.last_error = None
        return event

    def mark_rejected(self, *, event_id: str, at_ms: int, error: str | None = None) -> QueueEventRecord:
        event = self.get(event_id)
        event.state = QueueEventState.REJECTED
        event.acked_at_ms = at_ms
        event.last_error = (error or "").strip() or None
        return event

    def count_by_state(self) -> dict[str, int]:
        counts = {state.value: 0 for state in QueueEventState}
        for event_id in self._order:
            counts[self._events[event_id].state.value] += 1
        return counts
