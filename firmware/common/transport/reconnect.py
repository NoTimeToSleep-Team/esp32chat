from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Any

from ..protocol.codec import make_envelope
from ..protocol.constants import EndpointKind, MessageType
from .adapters import TransportAdapter
from .errors import TransportIOError
from .sync_push import SyncPushAttemptResult, SyncPushClient


@dataclass(frozen=True)
class ReconnectResult:
    session_valid: bool
    resync_required: bool
    push_result: SyncPushAttemptResult
    pulled_events_count: int
    next_cursor: str | None
    has_more: bool
    ack_sent: bool
    error_code: str | None


class ReconnectSyncCoordinator:
    def __init__(
        self,
        *,
        adapter: TransportAdapter,
        sender_id: str,
        target_id: str = "main",
    ) -> None:
        self._adapter = adapter
        self._sender_id = sender_id
        self._target_id = target_id

    def restore(
        self,
        *,
        push_client: SyncPushClient,
        is_session_valid: Callable[[], bool],
        since_cursor: str,
        now_ms: int,
        pull_limit: int = 100,
        channels: list[str] | None = None,
    ) -> ReconnectResult:
        if not is_session_valid():
            return ReconnectResult(
                session_valid=False,
                resync_required=False,
                push_result=SyncPushAttemptResult(
                    attempted_event_ids=(),
                    sent_count=0,
                    acked_count=0,
                    duplicate_count=0,
                    rejected_count=0,
                    retry_scheduled_count=0,
                    response_message_type=None,
                    error_code="session_invalid",
                    next_cursor=None,
                ),
                pulled_events_count=0,
                next_cursor=None,
                has_more=False,
                ack_sent=False,
                error_code="session_invalid",
            )

        push_result = push_client.attempt(
            base_cursor=since_cursor,
            now_ms=now_ms,
            limit=pull_limit,
        )

        pull_data = self._pull(
            since_cursor=since_cursor,
            now_ms=now_ms + 1,
            limit=pull_limit,
            channels=channels or [],
        )

        if pull_data["error_code"] is not None:
            return ReconnectResult(
                session_valid=True,
                resync_required=bool(pull_data["resync_required"]),
                push_result=push_result,
                pulled_events_count=0,
                next_cursor=None,
                has_more=False,
                ack_sent=False,
                error_code=str(pull_data["error_code"]),
            )

        events = pull_data["events"]
        if not isinstance(events, list):
            events = []
        received_event_ids = self._extract_event_ids(events)
        ack_sent = self._send_ack(
            applied_cursor=str(pull_data["next_cursor"]),
            received_event_ids=received_event_ids,
            now_ms=now_ms + 2,
        )

        return ReconnectResult(
            session_valid=True,
            resync_required=False,
            push_result=push_result,
            pulled_events_count=len(events),
            next_cursor=str(pull_data["next_cursor"]),
            has_more=bool(pull_data["has_more"]),
            ack_sent=ack_sent,
            error_code=None,
        )

    def _pull(
        self,
        *,
        since_cursor: str,
        now_ms: int,
        limit: int,
        channels: list[str],
    ) -> dict[str, Any]:
        envelope = make_envelope(
            message_type=MessageType.SYNC_PULL_REQUEST,
            sender_kind=EndpointKind.DEVICE,
            sender_id=self._sender_id,
            target_kind=EndpointKind.SERVER,
            target_id=self._target_id,
            sent_at_ms=now_ms,
            payload={
                "since_cursor": since_cursor,
                "limit": limit,
                "channels": channels,
            },
        )

        try:
            response = self._adapter.send(envelope)
        except TransportIOError:
            return {
                "error_code": "transport_io_error",
                "resync_required": False,
            }

        if response.message_type == MessageType.SYNC_PULL_RESPONSE.value:
            payload = response.payload
            return {
                "error_code": None,
                "events": payload.get("events") if isinstance(payload, dict) else [],
                "next_cursor": payload.get("next_cursor") if isinstance(payload, dict) else since_cursor,
                "has_more": payload.get("has_more") if isinstance(payload, dict) else False,
                "resync_required": False,
            }

        if response.message_type == MessageType.ERROR_RESPONSE.value:
            payload = response.payload
            if not isinstance(payload, dict):
                return {
                    "error_code": "error_response",
                    "resync_required": False,
                }

            error_payload = payload.get("error")
            if not isinstance(error_payload, dict):
                return {
                    "error_code": "error_response",
                    "resync_required": False,
                }

            code = error_payload.get("code")
            if code == "resync_required":
                return {
                    "error_code": "resync_required",
                    "resync_required": True,
                }

            return {
                "error_code": str(code) if isinstance(code, str) else "error_response",
                "resync_required": False,
            }

        return {
            "error_code": "unexpected_pull_response",
            "resync_required": False,
        }

    def _send_ack(self, *, applied_cursor: str, received_event_ids: list[str], now_ms: int) -> bool:
        envelope = make_envelope(
            message_type=MessageType.SYNC_ACK,
            sender_kind=EndpointKind.DEVICE,
            sender_id=self._sender_id,
            target_kind=EndpointKind.SERVER,
            target_id=self._target_id,
            sent_at_ms=now_ms,
            correlation_id=None,
            payload={
                "applied_cursor": applied_cursor,
                "received_event_ids": received_event_ids,
            },
        )

        try:
            self._adapter.send(envelope)
            return True
        except TransportIOError:
            return False

    @staticmethod
    def _extract_event_ids(events: list[Any]) -> list[str]:
        ids: list[str] = []
        for event in events:
            if not isinstance(event, dict):
                continue
            event_id = event.get("event_id")
            if isinstance(event_id, str) and event_id:
                ids.append(event_id)
        return ids
