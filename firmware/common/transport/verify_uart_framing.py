from __future__ import annotations

from firmware.common.transport.errors import TransportProtocolError
from firmware.common.transport.uart_framing import (
    FLAG_ACK_REQUIRED,
    UartFrameStreamParser,
    build_ack_frame,
    build_uart_frame,
    parse_uart_frame,
)


def main() -> None:
    frame_a = build_uart_frame(payload=b"hello-uart", sequence=42, flags=FLAG_ACK_REQUIRED)
    frame_b = build_uart_frame(payload=b"chunked-frame", sequence=43, flags=0)
    ack = build_ack_frame(sequence=43)

    parsed_a = parse_uart_frame(frame_a)
    if parsed_a.sequence != 42 or parsed_a.payload != b"hello-uart":
        raise RuntimeError("frame_a parse mismatch")

    stream = UartFrameStreamParser()
    merged = frame_a + frame_b + ack
    chunks = [merged[:5], merged[5:19], merged[19:37], merged[37:]]

    collected = []
    for chunk in chunks:
        collected.extend(stream.feed(chunk))

    if len(collected) != 3:
        raise RuntimeError("stream parser should emit 3 frames")
    if collected[1].payload != b"chunked-frame":
        raise RuntimeError("frame_b payload mismatch")
    if collected[2].payload != b"":
        raise RuntimeError("ack payload must be empty")

    bad = bytearray(frame_a)
    bad[-1] ^= 0x55
    crc_error = False
    try:
        parse_uart_frame(bytes(bad))
    except TransportProtocolError:
        crc_error = True
    if not crc_error:
        raise RuntimeError("crc error must be detected")

    print("UART_FRAME_COUNT", len(collected))
    print("UART_SEQUENCES", [item.sequence for item in collected])
    print("UART_ACK_FLAGS", collected[2].flags)
    print("UART_CRC_GUARD", crc_error)


if __name__ == "__main__":
    main()
