from __future__ import annotations

from firmware.common.protocol.codec import from_json, make_envelope, to_json
from firmware.common.protocol.constants import EndpointKind, MessageType
from firmware.common.transport.errors import TransportProtocolError
from firmware.common.transport.uart_adapter import UartFramedTransportAdapter
from firmware.common.transport.uart_framing import FLAG_ACK_REQUIRED, build_ack_frame, build_uart_frame, parse_uart_frame


def _build_response(request_frame: bytes, *, include_ack: bool, expect_ack_required: bool) -> bytes:
    parsed = parse_uart_frame(request_frame)
    has_ack_required = (parsed.flags & FLAG_ACK_REQUIRED) != 0
    if expect_ack_required and not has_ack_required:
        raise RuntimeError("request frame must ask for ACK")
    if (not expect_ack_required) and has_ack_required:
        raise RuntimeError("request frame must not ask for ACK")

    request_envelope = from_json(parsed.payload.decode("ascii"))
    response = make_envelope(
        message_type=MessageType.SYNC_PULL_RESPONSE,
        sender_kind=EndpointKind.SERVER,
        sender_id="main",
        target_kind=EndpointKind.DEVICE,
        target_id=request_envelope.sender.endpoint_id,
        sent_at_ms=request_envelope.sent_at_ms + 1,
        correlation_id=request_envelope.message_id,
        payload={
            "status": "ok",
            "events": [],
            "next_cursor": "cur-501",
            "has_more": False,
            "server_time_ms": request_envelope.sent_at_ms + 1,
        },
    )
    response_frame = build_uart_frame(
        payload=to_json(response).encode("ascii"),
        sequence=parsed.sequence,
        flags=0,
    )
    if include_ack:
        return build_ack_frame(sequence=parsed.sequence) + response_frame
    return response_frame


def main() -> None:
    adapter = UartFramedTransportAdapter(
        exchange=lambda frame: _build_response(frame, include_ack=True, expect_ack_required=True),
        require_ack=True,
    )

    request = make_envelope(
        message_type=MessageType.SYNC_PULL_REQUEST,
        sender_kind=EndpointKind.DEVICE,
        sender_id="m5cardputer-01",
        target_kind=EndpointKind.SERVER,
        target_id="main",
        sent_at_ms=1000,
        payload={
            "since_cursor": "cur-500",
            "limit": 50,
            "channels": ["chat-general"],
        },
    )

    response = adapter.send(request)
    if response.message_type != MessageType.SYNC_PULL_RESPONSE.value:
        raise RuntimeError("uart adapter response type mismatch")
    if response.payload.get("next_cursor") != "cur-501":
        raise RuntimeError("uart adapter next_cursor mismatch")

    ack_guard = False
    strict_adapter = UartFramedTransportAdapter(
        exchange=lambda frame: _build_response(frame, include_ack=False, expect_ack_required=True),
        require_ack=True,
    )
    try:
        strict_adapter.send(request)
    except TransportProtocolError:
        ack_guard = True
    if not ack_guard:
        raise RuntimeError("ack guard must reject missing ACK")

    relaxed_adapter = UartFramedTransportAdapter(
        exchange=lambda frame: _build_response(frame, include_ack=False, expect_ack_required=False),
        require_ack=False,
    )
    relaxed_response = relaxed_adapter.send(request)
    if relaxed_response.message_type != MessageType.SYNC_PULL_RESPONSE.value:
        raise RuntimeError("relaxed uart adapter response type mismatch")

    print("UART_ADAPTER_SYNC_PULL", response.message_type, response.payload.get("next_cursor"))
    print("UART_ADAPTER_ACK_GUARD", ack_guard)
    print("UART_ADAPTER_RELAXED", relaxed_response.message_type)


if __name__ == "__main__":
    main()
