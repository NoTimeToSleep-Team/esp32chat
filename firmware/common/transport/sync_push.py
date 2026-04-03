from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..protocol.codec import make_envelope
from ..protocol.constants import EndpointKind, MessageType
from ..protocol.idempotency import format_idempotency_key
from ..queue import LocalEventQueue
from ..queue.models import QueueEventRecord
from .adapters import TransportAdapter
from .errors import TransportIOError
from .retry import RetryPolicy


@dataclass(frozen=True)
class SyncPushAttemptResult:
    attempted_event_ids: tuple[str, ...]
    sent_count: int
    acked_count: int
    duplicate_count: int
    rejected_count: int
    retry_scheduled_count: int
    response_message_type: str | None
    error_code: str | None
    next_cursor: str | None


class SyncPushClient:
    def __init__(
        self,
        *,
        queue: LocalEventQueue,
        adapter: TransportAdapter,
        retry_policy: RetryPolicy,
        sender_id: str,
        boot_id: str,
        target_id: str = "main",
    ) -> None:
        self._queue = queue
        self._adapter = adapter
        self._retry_policy = retry_policy
        self._sender_id = sender_id
        self._boot_id = boot_id
        self._target_id = target_id
        self._counter = 0

    def attempt(self, *, base_cursor: str, now_ms: int, limit: int = 100) -> SyncPushAttemptResult:
        events = self._queue.get_retry_ready(
            now_ms=now_ms,
            retry_gate=self._retry_policy,
            limit=limit,
        )
        if not events:
            return SyncPushAttemptResult(
                attempted_event_ids=(),
                sent_count=0,
                acked_count=0,
                duplicate_count=0,
                rejected_count=0,
                retry_scheduled_count=0,
                response_message_type=None,
                error_code=None,
                next_cursor=None,
            )

        attempted_event_ids = tuple(event.event_id for event in events)
        for event in events:
            self._queue.mark_sent(event_id=event.event_id, attempt_ms=now_ms)

        self._counter += 1
        envelope = make_envelope(
            message_type=MessageType.SYNC_PUSH_REQUEST,
            sender_kind=EndpointKind.DEVICE,
            sender_id=self._sender_id,
            target_kind=EndpointKind.SERVER,
            target_id=self._target_id,
            sent_at_ms=now_ms,
            idempotency_key=format_idempotency_key(self._sender_id, self._boot_id, self._counter),
            payload={
                "base_cursor": base_cursor,
                "events": [self._event_payload(item) for item in events],
            },
        )

        try:
            response = self._adapter.send(envelope)
        except TransportIOError:
            for event_id in attempted_event_ids:
                self._queue.mark_retryable(
                    event_id=event_id,
                    at_ms=now_ms,
                    error="transport_io_error",
                )
            return SyncPushAttemptResult(
                attempted_event_ids=attempted_event_ids,
                sent_count=len(attempted_event_ids),
                acked_count=0,
                duplicate_count=0,
                rejected_count=0,
                retry_scheduled_count=len(attempted_event_ids),
                response_message_type=None,
                error_code="transport_io_error",
                next_cursor=None,
            )
        except Exception as exc:
            for event_id in attempted_event_ids:
                self._queue.mark_retryable(
                    event_id=event_id,
                    at_ms=now_ms,
                    error=str(exc),
                )
            return SyncPushAttemptResult(
                attempted_event_ids=attempted_event_ids,
                sent_count=len(attempted_event_ids),
                acked_count=0,
                duplicate_count=0,
                rejected_count=0,
                retry_scheduled_count=len(attempted_event_ids),
                response_message_type=None,
                error_code="transport_error",
                next_cursor=None,
            )

        if response.message_type == MessageType.SYNC_PUSH_RESPONSE.value:
            return self._handle_sync_push_response(
                attempted_event_ids=attempted_event_ids,
                response_payload=response.payload,
                now_ms=now_ms,
            )

        if response.message_type == MessageType.ERROR_RESPONSE.value:
            return self._handle_error_response(
                attempted_event_ids=attempted_event_ids,
                response_payload=response.payload,
                now_ms=now_ms,
            )

        for event_id in attempted_event_ids:
            self._queue.mark_retryable(
                event_id=event_id,
                at_ms=now_ms,
                error=f"unexpected_response:{response.message_type}",
            )
        return SyncPushAttemptResult(
            attempted_event_ids=attempted_event_ids,
            sent_count=len(attempted_event_ids),
            acked_count=0,
            duplicate_count=0,
            rejected_count=0,
            retry_scheduled_count=len(attempted_event_ids),
            response_message_type=response.message_type,
            error_code="unexpected_response",
            next_cursor=None,
        )

    def _handle_sync_push_response(
        self,
        *,
        attempted_event_ids: tuple[str, ...],
        response_payload: dict[str, Any],
        now_ms: int,
    ) -> SyncPushAttemptResult:
        attempted_set = set(attempted_event_ids)

        applied_ids = set(self._as_id_list(response_payload.get("applied_event_ids")))
        duplicate_ids = set(self._as_id_list(response_payload.get("duplicate_event_ids")))
        rejected_ids = set(self._extract_rejected_ids(response_payload.get("rejected")))

        acked_count = 0
        duplicate_count = 0
        rejected_count = 0

        handled: set[str] = set()

        for event_id in sorted(applied_ids & attempted_set):
            self._queue.mark_acked(event_id=event_id, acked_at_ms=now_ms)
            acked_count += 1
            handled.add(event_id)

        for event_id in sorted(duplicate_ids & attempted_set):
            self._queue.mark_duplicate(event_id=event_id, acked_at_ms=now_ms)
            duplicate_count += 1
            handled.add(event_id)

        for event_id in sorted(rejected_ids & attempted_set):
            self._queue.mark_rejected(event_id=event_id, at_ms=now_ms, error="rejected_by_server")
            rejected_count += 1
            handled.add(event_id)

        retry_scheduled_count = 0
        for event_id in attempted_event_ids:
            if event_id in handled:
                continue
            self._queue.mark_retryable(event_id=event_id, at_ms=now_ms, error="not_confirmed")
            retry_scheduled_count += 1

        next_cursor = response_payload.get("next_cursor")
        return SyncPushAttemptResult(
            attempted_event_ids=attempted_event_ids,
            sent_count=len(attempted_event_ids),
            acked_count=acked_count,
            duplicate_count=duplicate_count,
            rejected_count=rejected_count,
            retry_scheduled_count=retry_scheduled_count,
            response_message_type=MessageType.SYNC_PUSH_RESPONSE.value,
            error_code=None,
            next_cursor=str(next_cursor) if isinstance(next_cursor, str) else None,
        )

    def _handle_error_response(
        self,
        *,
        attempted_event_ids: tuple[str, ...],
        response_payload: dict[str, Any],
        now_ms: int,
    ) -> SyncPushAttemptResult:
        error_payload = response_payload.get("error")
        error_code = "error_response"
        retryable = True
        error_message = "error_response"

        if isinstance(error_payload, dict):
            code_value = error_payload.get("code")
            message_value = error_payload.get("message")
            retryable_value = error_payload.get("retryable")
            if isinstance(code_value, str):
                error_code = code_value
            if isinstance(message_value, str):
                error_message = message_value
            if isinstance(retryable_value, bool):
                retryable = retryable_value

        retry_scheduled_count = 0
        rejected_count = 0

        for event_id in attempted_event_ids:
            if retryable:
                self._queue.mark_retryable(event_id=event_id, at_ms=now_ms, error=error_message)
                retry_scheduled_count += 1
            else:
                self._queue.mark_rejected(event_id=event_id, at_ms=now_ms, error=error_message)
                rejected_count += 1

        return SyncPushAttemptResult(
            attempted_event_ids=attempted_event_ids,
            sent_count=len(attempted_event_ids),
            acked_count=0,
            duplicate_count=0,
            rejected_count=rejected_count,
            retry_scheduled_count=retry_scheduled_count,
            response_message_type=MessageType.ERROR_RESPONSE.value,
            error_code=error_code,
            next_cursor=None,
        )

    @staticmethod
    def _as_id_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        ids: list[str] = []
        for item in value:
            if isinstance(item, str) and item:
                ids.append(item)
        return ids

    @staticmethod
    def _extract_rejected_ids(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []

        rejected_ids: list[str] = []
        for item in value:
            if isinstance(item, str) and item:
                rejected_ids.append(item)
            elif isinstance(item, dict):
                event_id = item.get("event_id")
                if isinstance(event_id, str) and event_id:
                    rejected_ids.append(event_id)
        return rejected_ids

    @staticmethod
    def _event_payload(event: QueueEventRecord) -> dict[str, Any]:
        return {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "event_ts_ms": event.event_ts_ms,
            "payload_hash": event.payload_hash,
            "payload": event.payload,
        }
