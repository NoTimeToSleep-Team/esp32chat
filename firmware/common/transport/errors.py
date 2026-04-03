from __future__ import annotations


class TransportError(RuntimeError):
    pass


class TransportIOError(TransportError):
    """Transient IO/network failure while sending payload."""


class TransportProtocolError(TransportError):
    """Protocol-level response cannot be interpreted."""
