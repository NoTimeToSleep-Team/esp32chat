from __future__ import annotations

import json
import uuid
from typing import Any, Mapping

from .constants import (
    EndpointKind,
    MUTATING_MESSAGE_TYPES,
    PROTOCOL_VERSION,
    SUPPORTED_PROTOCOL_MAJOR,
    MessageType,
)
from .errors import (
    ProtocolValidationError,
    ProtocolVersionError,
    UnsupportedMessageTypeError,
)
from .idempotency import is_valid_idempotency_key
from .models import Endpoint, Envelope
from .schema import validate_payload_shape


def new_message_id() -> str:
    return f"msg-{uuid.uuid4().hex.upper()}"


def from_json(raw_json: str) -> Envelope:
    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ProtocolValidationError(f"invalid JSON payload: {exc}") from exc

    if not isinstance(parsed, Mapping):
        raise ProtocolValidationError("envelope must be a JSON object")
    return from_mapping(parsed)


def to_json(envelope: Envelope) -> str:
    validated = from_mapping(envelope.to_dict())
    return json.dumps(
        validated.to_dict(),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def from_mapping(raw: Mapping[str, Any]) -> Envelope:
    protocol_version = _read_required_ascii_string(raw, "protocol_version")
    _validate_protocol_version(protocol_version)

    message_type_text = _read_required_ascii_string(raw, "message_type")
    message_type = _validate_message_type(message_type_text)

    message_id = _read_required_ascii_string(raw, "message_id")
    correlation_id = _read_optional_ascii_string(raw, "correlation_id")

    idempotency_key = _read_optional_ascii_string(raw, "idempotency_key")
    _validate_idempotency_policy(message_type, idempotency_key)

    sender = _read_endpoint(raw, "sender")
    target = _read_endpoint(raw, "target")

    sent_at_ms = raw.get("sent_at_ms")
    if not isinstance(sent_at_ms, int):
        raise ProtocolValidationError("sent_at_ms must be integer milliseconds")
    if sent_at_ms < 0:
        raise ProtocolValidationError("sent_at_ms must be >= 0")

    payload_raw = raw.get("payload")
    if not isinstance(payload_raw, Mapping):
        raise ProtocolValidationError("payload must be an object")
    payload = dict(payload_raw)
    validate_payload_shape(message_type, payload)

    return Envelope(
        protocol_version=protocol_version,
        message_type=message_type.value,
        message_id=message_id,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        sender=sender,
        target=target,
        sent_at_ms=sent_at_ms,
        payload=payload,
    )


def make_envelope(
    *,
    message_type: MessageType,
    sender_kind: EndpointKind,
    sender_id: str,
    target_kind: EndpointKind,
    target_id: str,
    sent_at_ms: int,
    payload: Mapping[str, Any],
    message_id: str | None = None,
    idempotency_key: str | None = None,
    correlation_id: str | None = None,
) -> Envelope:
    envelope = {
        "protocol_version": PROTOCOL_VERSION,
        "message_type": message_type.value,
        "message_id": message_id or new_message_id(),
        "idempotency_key": idempotency_key,
        "correlation_id": correlation_id,
        "sender": {
            "kind": sender_kind.value,
            "id": sender_id,
        },
        "target": {
            "kind": target_kind.value,
            "id": target_id,
        },
        "sent_at_ms": sent_at_ms,
        "payload": dict(payload),
    }
    return from_mapping(envelope)


def _read_endpoint(raw: Mapping[str, Any], field_name: str) -> Endpoint:
    endpoint = raw.get(field_name)
    if not isinstance(endpoint, Mapping):
        raise ProtocolValidationError(f"{field_name} must be an object")

    kind = _read_required_ascii_string(endpoint, "kind")
    endpoint_id = _read_required_ascii_string(endpoint, "id")
    _validate_endpoint_kind(kind)

    return Endpoint(kind=kind, endpoint_id=endpoint_id)


def _read_required_ascii_string(
    raw: Mapping[str, Any],
    field_name: str,
) -> str:
    if field_name not in raw:
        raise ProtocolValidationError(f"missing envelope field: {field_name}")

    value = raw.get(field_name)
    if value is None:
        raise ProtocolValidationError(f"{field_name} must not be null")

    if not isinstance(value, str):
        raise ProtocolValidationError(f"{field_name} must be a string")

    text = value.strip()
    if not text:
        raise ProtocolValidationError(f"{field_name} must not be empty")

    try:
        text.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ProtocolValidationError(f"{field_name} must use ASCII characters") from exc

    return text


def _read_optional_ascii_string(raw: Mapping[str, Any], field_name: str) -> str | None:
    if field_name not in raw:
        raise ProtocolValidationError(f"missing envelope field: {field_name}")
    value = raw.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProtocolValidationError(f"{field_name} must be a string or null")
    text = value.strip()
    if not text:
        raise ProtocolValidationError(f"{field_name} must not be empty when present")
    try:
        text.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ProtocolValidationError(f"{field_name} must use ASCII characters") from exc
    return text


def _validate_message_type(value: str) -> MessageType:
    try:
        return MessageType(value)
    except ValueError as exc:
        raise UnsupportedMessageTypeError(f"unsupported message_type: {value}") from exc


def _validate_protocol_version(value: str) -> None:
    parts = value.split(".")
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        raise ProtocolVersionError("protocol_version must follow major.minor format")

    major = int(parts[0])
    if major != SUPPORTED_PROTOCOL_MAJOR:
        raise ProtocolVersionError(
            f"unsupported protocol major version: {major}, expected {SUPPORTED_PROTOCOL_MAJOR}"
        )


def _validate_endpoint_kind(value: str) -> None:
    allowed = {item.value for item in EndpointKind}
    if value not in allowed:
        raise ProtocolValidationError(
            f"endpoint kind must be one of: {', '.join(sorted(allowed))}"
        )


def _validate_idempotency_policy(
    message_type: MessageType,
    idempotency_key: str | None,
) -> None:
    if message_type in MUTATING_MESSAGE_TYPES:
        if not is_valid_idempotency_key(idempotency_key):
            raise ProtocolValidationError(
                f"idempotency_key is required for mutating message type {message_type.value}"
            )
    elif idempotency_key is not None and not is_valid_idempotency_key(idempotency_key):
        raise ProtocolValidationError("idempotency_key must follow <sender_id>:<boot_id>:<counter>")
