from __future__ import annotations

import zlib
from dataclasses import dataclass

from .errors import TransportProtocolError

START_BYTE = 0x7E
FRAME_VERSION = 1

FLAG_ACK_REQUIRED = 0x01
FLAG_ACK = 0x02

MAX_PAYLOAD_SIZE = 4096

_HEADER_SIZE = 7
_CRC_SIZE = 4
_MIN_FRAME_SIZE = _HEADER_SIZE + _CRC_SIZE


@dataclass(frozen=True)
class UartFrame:
    version: int
    flags: int
    sequence: int
    payload: bytes
    crc32: int


def build_uart_frame(*, payload: bytes, sequence: int, flags: int = 0, version: int = FRAME_VERSION) -> bytes:
    if not isinstance(payload, (bytes, bytearray)):
        raise TransportProtocolError("payload must be bytes")
    if not 0 <= sequence <= 0xFFFF:
        raise TransportProtocolError("sequence out of range")
    if not 0 <= flags <= 0xFF:
        raise TransportProtocolError("flags out of range")
    if not 0 <= version <= 0xFF:
        raise TransportProtocolError("version out of range")
    if len(payload) > MAX_PAYLOAD_SIZE:
        raise TransportProtocolError("payload too large")

    header = bytes(
        [
            START_BYTE,
            version,
            flags,
            (sequence >> 8) & 0xFF,
            sequence & 0xFF,
            (len(payload) >> 8) & 0xFF,
            len(payload) & 0xFF,
        ]
    )
    crc_data = header[1:] + bytes(payload)
    checksum = zlib.crc32(crc_data) & 0xFFFFFFFF
    return header + bytes(payload) + checksum.to_bytes(4, "big")


def build_ack_frame(*, sequence: int, version: int = FRAME_VERSION) -> bytes:
    return build_uart_frame(payload=b"", sequence=sequence, flags=FLAG_ACK, version=version)


def parse_uart_frame(frame_bytes: bytes) -> UartFrame:
    if len(frame_bytes) < _MIN_FRAME_SIZE:
        raise TransportProtocolError("frame too short")
    if frame_bytes[0] != START_BYTE:
        raise TransportProtocolError("invalid start byte")

    version = frame_bytes[1]
    flags = frame_bytes[2]
    sequence = (frame_bytes[3] << 8) | frame_bytes[4]
    payload_len = (frame_bytes[5] << 8) | frame_bytes[6]

    if payload_len > MAX_PAYLOAD_SIZE:
        raise TransportProtocolError("payload too large")

    expected_size = _HEADER_SIZE + payload_len + _CRC_SIZE
    if len(frame_bytes) != expected_size:
        raise TransportProtocolError("frame size mismatch")

    payload_start = _HEADER_SIZE
    payload_end = payload_start + payload_len
    payload = frame_bytes[payload_start:payload_end]
    received_crc = int.from_bytes(frame_bytes[payload_end:payload_end + 4], "big")
    calculated_crc = zlib.crc32(frame_bytes[1:payload_end]) & 0xFFFFFFFF
    if received_crc != calculated_crc:
        raise TransportProtocolError("crc mismatch")

    return UartFrame(
        version=version,
        flags=flags,
        sequence=sequence,
        payload=payload,
        crc32=received_crc,
    )


class UartFrameStreamParser:
    def __init__(self, *, max_buffer_size: int = 16384) -> None:
        self._buffer = bytearray()
        self._max_buffer_size = max_buffer_size

    def feed(self, data: bytes) -> list[UartFrame]:
        if not isinstance(data, (bytes, bytearray)):
            raise TransportProtocolError("stream chunk must be bytes")

        self._buffer.extend(data)
        parsed: list[UartFrame] = []

        while True:
            start_index = self._buffer.find(bytes([START_BYTE]))
            if start_index < 0:
                self._buffer.clear()
                break
            if start_index > 0:
                del self._buffer[:start_index]

            if len(self._buffer) < _MIN_FRAME_SIZE:
                break

            payload_len = (self._buffer[5] << 8) | self._buffer[6]
            if payload_len > MAX_PAYLOAD_SIZE:
                del self._buffer[0]
                continue

            frame_size = _HEADER_SIZE + payload_len + _CRC_SIZE
            if len(self._buffer) < frame_size:
                break

            candidate = bytes(self._buffer[:frame_size])
            try:
                frame = parse_uart_frame(candidate)
            except TransportProtocolError:
                del self._buffer[0]
                continue

            parsed.append(frame)
            del self._buffer[:frame_size]

        if len(self._buffer) > self._max_buffer_size:
            self._buffer = self._buffer[-_MIN_FRAME_SIZE:]

        return parsed
