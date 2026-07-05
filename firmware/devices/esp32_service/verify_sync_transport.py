from __future__ import annotations

from firmware.common.protocol.codec import from_json, make_envelope, to_json
from firmware.common.protocol.constants import EndpointKind, MessageType
from firmware.common.queue import QueueEventState
from firmware.common.transport import (
    FLAG_ACK_REQUIRED,
    build_ack_frame,
    build_uart_frame,
    parse_uart_frame,
)

from .config import Esp32ServiceConfig
from .controller import Esp32ServiceController
from .server_api import ServerOpsGateway
from .sync_transport import build_sync_transport_adapter


class _NoopSender:
    def send(self, *, method: str, path: str, query=None, json_payload=None) -> dict[str, object]:
        return {"status": "noop"}


def _build_sync_handler(state: dict[str, int]):
    def handler(envelope):
        message_type = MessageType(envelope.message_type)

        if message_type == MessageType.SYNC_PUSH_REQUEST:
            events = envelope.payload.get("events")
            applied_event_ids: list[str] = []
            if isinstance(events, list):
                for item in events:
                    if not isinstance(item, dict):
                        continue
                    event_id = item.get("event_id")
                    if isinstance(event_id, str) and event_id:
                        applied_event_ids.append(event_id)

            return make_envelope(
                message_type=MessageType.SYNC_PUSH_RESPONSE,
                sender_kind=EndpointKind.SERVER,
                sender_id="main",
                target_kind=EndpointKind.DEVICE,
                target_id=envelope.sender.endpoint_id,
                sent_at_ms=envelope.sent_at_ms + 1,
                correlation_id=envelope.message_id,
                payload={
                    "status": "ok",
                    "applied_event_ids": applied_event_ids,
                    "duplicate_event_ids": [],
                    "rejected": [],
                    "next_cursor": "cur-sync-1",
                    "server_time_ms": envelope.sent_at_ms + 1,
                },
            )

        if message_type == MessageType.SYNC_PULL_REQUEST:
            return make_envelope(
                message_type=MessageType.SYNC_PULL_RESPONSE,
                sender_kind=EndpointKind.SERVER,
                sender_id="main",
                target_kind=EndpointKind.DEVICE,
                target_id=envelope.sender.endpoint_id,
                sent_at_ms=envelope.sent_at_ms + 1,
                correlation_id=envelope.message_id,
                payload={
                    "status": "ok",
                    "events": [
                        {
                            "event_id": "evt-server-sync-1",
                            "event_type": "chat.message",
                            "event_ts_ms": envelope.sent_at_ms,
                            "payload": {
                                "chat_id": "chat-general",
                                "message_id": "msg-sync-1",
                                "author_user_id": "usr-1001",
                                "text": "sync restore event",
                            },
                        }
                    ],
                    "next_cursor": "cur-sync-2",
                    "has_more": False,
                    "server_time_ms": envelope.sent_at_ms + 1,
                },
            )

        if message_type == MessageType.SYNC_ACK:
            state["ack_count"] += 1
            return make_envelope(
                message_type=MessageType.SYNC_ACK,
                sender_kind=EndpointKind.SERVER,
                sender_id="main",
                target_kind=EndpointKind.DEVICE,
                target_id=envelope.sender.endpoint_id,
                sent_at_ms=envelope.sent_at_ms + 1,
                correlation_id=envelope.message_id,
                payload={
                    "applied_cursor": envelope.payload.get("applied_cursor", "cur-sync-2"),
                    "received_event_ids": envelope.payload.get("received_event_ids", []),
                },
            )

        return make_envelope(
            message_type=MessageType.ERROR_RESPONSE,
            sender_kind=EndpointKind.SERVER,
            sender_id="main",
            target_kind=EndpointKind.DEVICE,
            target_id=envelope.sender.endpoint_id,
            sent_at_ms=envelope.sent_at_ms + 1,
            correlation_id=envelope.message_id,
            payload={
                "error": {
                    "code": "unsupported_message_type",
                    "message": f"unsupported in verifier: {envelope.message_type}",
                    "retryable": False,
                },
                "server_time_ms": envelope.sent_at_ms + 1,
            },
        )

    return handler


def _build_uart_exchange(handler):
    def exchange(request_frame: bytes) -> bytes:
        parsed = parse_uart_frame(request_frame)
        request = from_json(parsed.payload.decode("ascii"))
        response = handler(request)
        response_frame = build_uart_frame(
            payload=to_json(response).encode("ascii"),
            sequence=parsed.sequence,
            flags=0,
        )
        if (parsed.flags & FLAG_ACK_REQUIRED) != 0:
            return build_ack_frame(sequence=parsed.sequence) + response_frame
        return response_frame

    return exchange


def _new_controller(config: Esp32ServiceConfig) -> Esp32ServiceController:
    return Esp32ServiceController(config=config, gateway=ServerOpsGateway(_NoopSender()))


def _enqueue_one(controller: Esp32ServiceController, *, suffix: str) -> str:
    event = controller.queue.enqueue(
        event_type="chat.send",
        event_ts_ms=1775300499001,
        idempotency_key=f"esp32-s3-01:boot-sync-{suffix}:0001",
        payload={
            "chat_id": "chat-general",
            "client_message_id": f"cmid-{suffix}",
            "text": f"sync-event-{suffix}",
        },
        event_id=f"evt-sync-{suffix}",
    )
    return event.event_id


def main() -> None:
    state: dict[str, int] = {"ack_count": 0}
    handler = _build_sync_handler(state)

    memory_config = Esp32ServiceConfig(boot_id="boot-sync-memory", sync_transport="inmemory")
    memory_controller = _new_controller(memory_config)
    memory_adapter = build_sync_transport_adapter(memory_config, envelope_handler=handler)
    memory_controller.attach_sync_adapter(adapter=memory_adapter)
    memory_event_id = _enqueue_one(memory_controller, suffix="mem")
    memory_push = memory_controller.sync_push_once(base_cursor="cur-sync-0", now_ms=2000)
    memory_counts = memory_controller.queue.count_by_state()

    uart_config = Esp32ServiceConfig(
        boot_id="boot-sync-uart",
        sync_transport="uart",
        sync_uart_ack_required=True,
    )
    uart_controller = _new_controller(uart_config)
    uart_adapter = build_sync_transport_adapter(
        uart_config,
        uart_exchange=_build_uart_exchange(handler),
    )
    uart_controller.attach_sync_adapter(adapter=uart_adapter)
    uart_event_id = _enqueue_one(uart_controller, suffix="uart")
    uart_push = uart_controller.sync_push_once(base_cursor="cur-sync-0", now_ms=3000)
    uart_restore = uart_controller.sync_restore(
        since_cursor="cur-sync-1",
        now_ms=3001,
        is_session_valid=lambda: True,
        pull_limit=50,
        channels=["chat-general"],
    )
    uart_counts = uart_controller.queue.count_by_state()

    invalid_transport_guard = False
    invalid_config = Esp32ServiceConfig(sync_transport="i2c")
    try:
        build_sync_transport_adapter(invalid_config)
    except RuntimeError:
        invalid_transport_guard = True

    if memory_push.acked_count != 1 or memory_push.retry_scheduled_count != 0:
        raise RuntimeError("memory sync push result mismatch")
    if memory_counts[QueueEventState.ACKED.value] != 1:
        raise RuntimeError("memory queue ack state mismatch")
    if memory_controller.queue.get(memory_event_id).state != QueueEventState.ACKED:
        raise RuntimeError("memory event state mismatch")

    if uart_push.acked_count != 1 or uart_push.retry_scheduled_count != 0:
        raise RuntimeError("uart sync push result mismatch")
    if uart_counts[QueueEventState.ACKED.value] != 1:
        raise RuntimeError("uart queue ack state mismatch")
    if uart_controller.queue.get(uart_event_id).state != QueueEventState.ACKED:
        raise RuntimeError("uart event state mismatch")
    if not uart_restore.ack_sent or uart_restore.pulled_events_count != 1:
        raise RuntimeError("uart sync restore result mismatch")
    if state["ack_count"] < 1:
        raise RuntimeError("sync restore ack was not observed by handler")
    if not invalid_transport_guard:
        raise RuntimeError("invalid transport guard must reject unsupported sync transport")

    print("ESP32_SYNC_MEMORY", memory_push.acked_count, memory_push.next_cursor)
    print("ESP32_SYNC_UART", uart_push.acked_count, uart_push.next_cursor)
    print("ESP32_SYNC_RESTORE", uart_restore.pulled_events_count, uart_restore.ack_sent)
    print("ESP32_SYNC_ACK_COUNT", state["ack_count"])
    print("ESP32_SYNC_INVALID_TRANSPORT_GUARD", invalid_transport_guard)


if __name__ == "__main__":
    main()
