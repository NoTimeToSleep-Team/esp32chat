from __future__ import annotations

from collections.abc import Callable

from ..protocol.codec import from_json, to_json
from ..protocol.models import Envelope
from .errors import TransportIOError, TransportProtocolError
from .uart_framing import FLAG_ACK, FLAG_ACK_REQUIRED, UartFrame, UartFrameStreamParser, build_uart_frame


class UartFramedTransportAdapter:
    """Envelope transport over UART v1 framed byte exchange."""

    def __init__(
        self,
        *,
        exchange: Callable[[bytes], bytes],
        require_ack: bool = True,
        start_sequence: int = 0,
    ) -> None:
        if not 0 <= start_sequence <= 0xFFFF:
            raise TransportProtocolError("start_sequence out of range")
        self._exchange = exchange
        self._require_ack = require_ack
        self._sequence = start_sequence

    def send(self, envelope: Envelope) -> Envelope:
        sequence = self._sequence
        self._sequence = (self._sequence + 1) & 0xFFFF

        payload = to_json(envelope).encode("ascii")
        flags = FLAG_ACK_REQUIRED if self._require_ack else 0
        frame = build_uart_frame(payload=payload, sequence=sequence, flags=flags)

        try:
            response_bytes = self._exchange(frame)
        except Exception as exc:  # noqa: BLE001
            raise TransportIOError(str(exc) or "uart_exchange_failed") from exc

        if not isinstance(response_bytes, (bytes, bytearray)):
            raise TransportProtocolError("uart exchange must return bytes")

        frames = UartFrameStreamParser().feed(bytes(response_bytes))
        if not frames:
            raise TransportProtocolError("uart response does not contain a valid frame")

        ack_found = any((item.flags & FLAG_ACK) != 0 and item.sequence == sequence for item in frames)
        if self._require_ack and not ack_found:
            raise TransportProtocolError("uart ack not received for sent frame")

        response_frame = self._pick_payload_frame(frames)
        if response_frame is None:
            raise TransportProtocolError("uart response payload frame not found")

        try:
            payload_text = response_frame.payload.decode("ascii")
        except UnicodeDecodeError as exc:
            raise TransportProtocolError("uart payload must be ASCII JSON") from exc

        try:
            return from_json(payload_text)
        except Exception as exc:  # noqa: BLE001
            raise TransportProtocolError(str(exc) or "invalid uart envelope payload") from exc

    @staticmethod
    def _pick_payload_frame(frames: list[UartFrame]) -> UartFrame | None:
        for frame in frames:
            if (frame.flags & FLAG_ACK) != 0:
                continue
            return frame
        return None
