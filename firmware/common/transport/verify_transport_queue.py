from __future__ import annotations

from firmware.common.protocol.codec import make_envelope
from firmware.common.protocol.constants import EndpointKind, MessageType
from firmware.common.queue import LocalEventQueue, QueueEventState
from firmware.common.transport import (
    InMemoryTransportAdapter,
    ReconnectSyncCoordinator,
    RetryPolicy,
    SyncPushClient,
    TransportIOError,
)


def main() -> None:
    queue = LocalEventQueue()

    event_a = queue.enqueue(
        event_type="chat.send",
        event_ts_ms=1775300499001,
        idempotency_key="m5stickc-02:boot-h7g6f5:000301",
        payload={
            "chat_id": "chat-general",
            "client_message_id": "cmid-7781",
            "text": "Queued while offline A",
        },
        event_id="evt-000901",
    )
    duplicate_a = queue.enqueue(
        event_type="chat.send",
        event_ts_ms=1775300499001,
        idempotency_key="m5stickc-02:boot-h7g6f5:000301",
        payload={
            "chat_id": "chat-general",
            "client_message_id": "cmid-7781",
            "text": "Queued while offline A",
        },
    )
    event_b = queue.enqueue(
        event_type="chat.send",
        event_ts_ms=1775300499002,
        idempotency_key="m5stickc-02:boot-h7g6f5:000302",
        payload={
            "chat_id": "chat-general",
            "client_message_id": "cmid-7782",
            "text": "Queued while offline B",
        },
        event_id="evt-000902",
    )

    push_attempt_counter = {"count": 0}

    def handler(envelope):
        message_type = MessageType(envelope.message_type)

        if message_type == MessageType.SYNC_PUSH_REQUEST:
            push_attempt_counter["count"] += 1
            if push_attempt_counter["count"] == 1:
                raise TransportIOError("temporary_disconnect")

            return make_envelope(
                message_type=MessageType.SYNC_PUSH_RESPONSE,
                sender_kind=EndpointKind.SERVER,
                sender_id="main",
                target_kind=EndpointKind.DEVICE,
                target_id="m5stickc-02",
                sent_at_ms=envelope.sent_at_ms + 1,
                correlation_id=envelope.message_id,
                payload={
                    "status": "ok",
                    "applied_event_ids": [event_b.event_id],
                    "duplicate_event_ids": [event_a.event_id],
                    "rejected": [],
                    "next_cursor": "cur-000001221",
                    "server_time_ms": envelope.sent_at_ms + 1,
                },
            )

        if message_type == MessageType.SYNC_PULL_REQUEST:
            return make_envelope(
                message_type=MessageType.SYNC_PULL_RESPONSE,
                sender_kind=EndpointKind.SERVER,
                sender_id="main",
                target_kind=EndpointKind.DEVICE,
                target_id="m5stickc-02",
                sent_at_ms=envelope.sent_at_ms + 1,
                correlation_id=envelope.message_id,
                payload={
                    "status": "ok",
                    "events": [
                        {
                            "event_id": "evt-server-0001",
                            "event_type": "chat.message",
                            "event_ts_ms": envelope.sent_at_ms,
                            "payload": {
                                "chat_id": "chat-general",
                                "message_id": "msg-chat-009913",
                                "author_user_id": "usr-2002",
                                "text": "Welcome back",
                            },
                        }
                    ],
                    "next_cursor": "cur-000001222",
                    "has_more": False,
                    "server_time_ms": envelope.sent_at_ms + 1,
                },
            )

        if message_type == MessageType.SYNC_ACK:
            return make_envelope(
                message_type=MessageType.SYNC_ACK,
                sender_kind=EndpointKind.SERVER,
                sender_id="main",
                target_kind=EndpointKind.DEVICE,
                target_id="m5stickc-02",
                sent_at_ms=envelope.sent_at_ms + 1,
                correlation_id=envelope.message_id,
                payload={
                    "applied_cursor": envelope.payload["applied_cursor"],
                    "received_event_ids": envelope.payload["received_event_ids"],
                },
            )

        return make_envelope(
            message_type=MessageType.ERROR_RESPONSE,
            sender_kind=EndpointKind.SERVER,
            sender_id="main",
            target_kind=EndpointKind.DEVICE,
            target_id="m5stickc-02",
            sent_at_ms=envelope.sent_at_ms + 1,
            correlation_id=envelope.message_id,
            payload={
                "error": {
                    "code": "unsupported_message_type",
                    "message": f"Unsupported in verifier: {envelope.message_type}",
                    "retryable": False,
                },
                "server_time_ms": envelope.sent_at_ms + 1,
            },
        )

    adapter = InMemoryTransportAdapter(handler=handler)
    retry_policy = RetryPolicy(schedule_ms=(10, 20, 40, 80, 160, 300))

    push_client = SyncPushClient(
        queue=queue,
        adapter=adapter,
        retry_policy=retry_policy,
        sender_id="m5stickc-02",
        boot_id="boot-h7g6f5",
    )

    attempt_1 = push_client.attempt(base_cursor="cur-000001220", now_ms=1000)
    attempt_2 = push_client.attempt(base_cursor="cur-000001220", now_ms=1005)
    attempt_3 = push_client.attempt(base_cursor="cur-000001220", now_ms=1010)

    reconnect = ReconnectSyncCoordinator(
        adapter=adapter,
        sender_id="m5stickc-02",
    )
    reconnect_result = reconnect.restore(
        push_client=push_client,
        is_session_valid=lambda: True,
        since_cursor="cur-000001221",
        now_ms=2000,
        pull_limit=50,
        channels=["chat-general", "blog-feed"],
    )

    counts = queue.count_by_state()

    if attempt_1.error_code != "transport_io_error":
        raise RuntimeError("attempt_1 should fail with transport_io_error")
    if attempt_2.sent_count != 0:
        raise RuntimeError("attempt_2 should be backoff-blocked")
    if attempt_3.acked_count != 1 or attempt_3.duplicate_count != 1:
        raise RuntimeError("attempt_3 should ack one event and mark one duplicate")
    if counts[QueueEventState.REJECTED.value] != 0:
        raise RuntimeError("rejected events must remain zero in this scenario")
    if counts[QueueEventState.ACKED.value] != 1 or counts[QueueEventState.DUPLICATE.value] != 1:
        raise RuntimeError("final queue counts mismatch")
    if not reconnect_result.ack_sent or reconnect_result.pulled_events_count != 1:
        raise RuntimeError("reconnect flow failed")

    print("DUPLICATE_ENQUEUE_SAME_EVENT", duplicate_a.event_id == event_a.event_id)
    print("ATTEMPT1", attempt_1.sent_count, attempt_1.retry_scheduled_count, attempt_1.error_code)
    print("ATTEMPT2", attempt_2.sent_count, attempt_2.retry_scheduled_count, attempt_2.error_code)
    print(
        "ATTEMPT3",
        attempt_3.sent_count,
        attempt_3.acked_count,
        attempt_3.duplicate_count,
        attempt_3.rejected_count,
        attempt_3.retry_scheduled_count,
    )
    print("QUEUE_COUNTS", counts)
    print(
        "RECONNECT",
        reconnect_result.session_valid,
        reconnect_result.pulled_events_count,
        reconnect_result.next_cursor,
        reconnect_result.ack_sent,
        reconnect_result.error_code,
    )


if __name__ == "__main__":
    main()
