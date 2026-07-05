from __future__ import annotations

from firmware.common.protocol.codec import from_json, make_envelope, to_json
from firmware.common.protocol.constants import EndpointKind, MessageType
from firmware.common.queue import LocalEventQueue, QueueEventState
from firmware.common.transport.retry import RetryPolicy
from firmware.common.transport.sync_push import SyncPushClient
from firmware.common.transport.uart_adapter import UartFramedTransportAdapter
from firmware.common.transport.uart_framing import build_ack_frame, build_uart_frame, parse_uart_frame


def main() -> None:
    queue = LocalEventQueue()
    event = queue.enqueue(
        event_type="chat.send",
        event_ts_ms=1775300499001,
        idempotency_key="esp32-s3-01:boot-retry:0001",
        payload={
            "chat_id": "chat-general",
            "client_message_id": "cmid-retry-1",
            "text": "queued event for uart retry",
        },
        event_id="evt-uart-retry-1",
    )

    state = {
        "call_count": 0,
        "sequences": [],
    }

    def exchange(request_frame: bytes) -> bytes:
        parsed = parse_uart_frame(request_frame)
        state["call_count"] += 1
        state["sequences"].append(parsed.sequence)

        request = from_json(parsed.payload.decode("ascii"))
        if request.message_type != MessageType.SYNC_PUSH_REQUEST.value:
            raise RuntimeError("expected sync.push.request over UART retry verifier")

        if state["call_count"] == 1:
            raise OSError("simulated_uart_disconnect")

        events = request.payload.get("events")
        applied_event_ids: list[str] = []
        if isinstance(events, list):
            for item in events:
                if isinstance(item, dict):
                    event_id = item.get("event_id")
                    if isinstance(event_id, str) and event_id:
                        applied_event_ids.append(event_id)

        response = make_envelope(
            message_type=MessageType.SYNC_PUSH_RESPONSE,
            sender_kind=EndpointKind.SERVER,
            sender_id="main",
            target_kind=EndpointKind.DEVICE,
            target_id=request.sender.endpoint_id,
            sent_at_ms=request.sent_at_ms + 1,
            correlation_id=request.message_id,
            payload={
                "status": "ok",
                "applied_event_ids": applied_event_ids,
                "duplicate_event_ids": [],
                "rejected": [],
                "next_cursor": "cur-uart-retry-1",
                "server_time_ms": request.sent_at_ms + 1,
            },
        )
        response_frame = build_uart_frame(
            payload=to_json(response).encode("ascii"),
            sequence=parsed.sequence,
            flags=0,
        )
        return build_ack_frame(sequence=parsed.sequence) + response_frame

    adapter = UartFramedTransportAdapter(
        exchange=exchange,
        require_ack=True,
        start_sequence=0xFFFF,
    )
    push_client = SyncPushClient(
        queue=queue,
        adapter=adapter,
        retry_policy=RetryPolicy(schedule_ms=(1, 1, 1)),
        sender_id="esp32-s3-01",
        boot_id="boot-retry",
    )

    attempt_1 = push_client.attempt(base_cursor="cur-uart-0", now_ms=1000)
    attempt_2 = push_client.attempt(base_cursor="cur-uart-0", now_ms=1001)
    counts = queue.count_by_state()

    if attempt_1.error_code != "transport_io_error":
        raise RuntimeError("attempt_1 must fail with transport_io_error")
    if attempt_2.acked_count != 1 or attempt_2.retry_scheduled_count != 0:
        raise RuntimeError("attempt_2 must ACK queued event after retry")
    if queue.get(event.event_id).state != QueueEventState.ACKED:
        raise RuntimeError("event must be ACKED after second UART push attempt")
    if state["sequences"] != [65535, 0]:
        raise RuntimeError(f"expected UART sequence rollover [65535, 0], got {state['sequences']}")
    if counts[QueueEventState.ACKED.value] != 1:
        raise RuntimeError("queue acked count mismatch")

    print("UART_SYNC_RETRY_ATTEMPT1", attempt_1.error_code, attempt_1.retry_scheduled_count)
    print("UART_SYNC_RETRY_ATTEMPT2", attempt_2.acked_count, attempt_2.next_cursor)
    print("UART_SYNC_SEQUENCES", state["sequences"])
    print("UART_SYNC_QUEUE_COUNTS", counts)


if __name__ == "__main__":
    main()
