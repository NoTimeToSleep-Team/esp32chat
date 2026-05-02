"""Shared transport runtime for queue-based sync delivery."""

from .adapters import InMemoryTransportAdapter, SentFrame, TransportAdapter
from .errors import TransportError, TransportIOError, TransportProtocolError
from .reconnect import ReconnectResult, ReconnectSyncCoordinator
from .retry import RetryPolicy
from .sync_push import SyncPushAttemptResult, SyncPushClient
from .uart_adapter import UartFramedTransportAdapter
from .uart_framing import (
    FLAG_ACK,
    FLAG_ACK_REQUIRED,
    FRAME_VERSION,
    START_BYTE,
    UartFrame,
    UartFrameStreamParser,
    build_ack_frame,
    build_uart_frame,
    parse_uart_frame,
)

__all__ = [
    "InMemoryTransportAdapter",
    "ReconnectResult",
    "ReconnectSyncCoordinator",
    "RetryPolicy",
    "SentFrame",
    "SyncPushAttemptResult",
    "SyncPushClient",
    "UartFramedTransportAdapter",
    "START_BYTE",
    "TransportAdapter",
    "TransportError",
    "TransportIOError",
    "TransportProtocolError",
    "FRAME_VERSION",
    "FLAG_ACK",
    "FLAG_ACK_REQUIRED",
    "UartFrame",
    "UartFrameStreamParser",
    "build_uart_frame",
    "build_ack_frame",
    "parse_uart_frame",
]
