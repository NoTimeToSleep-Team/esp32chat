"""Shared protocol codec and validation utilities for firmware targets."""

from .codec import from_json, from_mapping, make_envelope, new_message_id, to_json
from .constants import (
    EndpointKind,
    ErrorCode,
    MessageType,
    PROTOCOL_VERSION,
    SUPPORTED_PROTOCOL_MAJOR,
)
from .errors import (
    ProtocolError,
    ProtocolValidationError,
    ProtocolVersionError,
    UnsupportedMessageTypeError,
)
from .idempotency import format_idempotency_key, is_valid_idempotency_key
from .models import Endpoint, Envelope

__all__ = [
    "Endpoint",
    "EndpointKind",
    "Envelope",
    "ErrorCode",
    "MessageType",
    "PROTOCOL_VERSION",
    "ProtocolError",
    "ProtocolValidationError",
    "ProtocolVersionError",
    "SUPPORTED_PROTOCOL_MAJOR",
    "UnsupportedMessageTypeError",
    "format_idempotency_key",
    "from_json",
    "from_mapping",
    "is_valid_idempotency_key",
    "make_envelope",
    "new_message_id",
    "to_json",
]
