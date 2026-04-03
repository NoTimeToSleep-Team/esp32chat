from __future__ import annotations

from typing import Any, Mapping, cast

from .constants import ErrorCode, MessageType
from .errors import ProtocolValidationError


_REQUIRED_PAYLOAD_FIELDS: dict[MessageType, tuple[str, ...]] = {
    MessageType.DEVICE_REGISTER_REQUEST: (
        "device_uid",
        "device_type",
        "firmware_version",
        "boot_id",
        "capabilities",
    ),
    MessageType.DEVICE_REGISTER_RESPONSE: (
        "status",
        "sync_profile",
        "server_time_ms",
    ),
    MessageType.DEVICE_HEARTBEAT: (
        "uptime_ms",
        "status",
        "queue_depth",
    ),
    MessageType.TELEMETRY_SNAPSHOT: (
        "power",
        "temperature",
        "service_flags",
    ),
    MessageType.AUTH_LOGIN_REQUEST: (
        "login",
        "password",
        "device_fingerprint",
        "client_mode",
    ),
    MessageType.AUTH_LOGIN_RESPONSE: (
        "status",
        "role",
        "mode",
        "server_time_ms",
    ),
    MessageType.CHAT_SEND_REQUEST: (
        "chat_id",
        "client_message_id",
        "text",
    ),
    MessageType.CHAT_SEND_RESPONSE: (
        "status",
        "message_id",
        "server_seq",
        "created_at_ms",
    ),
    MessageType.CHAT_MESSAGE_EVENT: (
        "chat_id",
        "message_id",
        "server_seq",
        "author_user_id",
        "text",
        "created_at_ms",
    ),
    MessageType.SYNC_PUSH_REQUEST: (
        "base_cursor",
        "events",
    ),
    MessageType.SYNC_PUSH_RESPONSE: (
        "status",
        "applied_event_ids",
        "duplicate_event_ids",
        "rejected",
        "next_cursor",
        "server_time_ms",
    ),
    MessageType.SYNC_PULL_REQUEST: (
        "since_cursor",
        "limit",
    ),
    MessageType.SYNC_PULL_RESPONSE: (
        "status",
        "events",
        "next_cursor",
        "has_more",
        "server_time_ms",
    ),
    MessageType.SYNC_ACK: (
        "applied_cursor",
        "received_event_ids",
    ),
    MessageType.ERROR_RESPONSE: (
        "error",
        "server_time_ms",
    ),
}


def validate_payload_shape(message_type: MessageType, payload: Mapping[str, Any]) -> None:
    required = _REQUIRED_PAYLOAD_FIELDS[message_type]
    missing = [field for field in required if field not in payload]
    if missing:
        raise ProtocolValidationError(
            f"payload missing required fields for {message_type.value}: {', '.join(missing)}"
        )

    if message_type == MessageType.DEVICE_REGISTER_REQUEST:
        _assert_mapping(payload.get("capabilities"), "payload.capabilities")

    if message_type == MessageType.DEVICE_REGISTER_RESPONSE:
        status = payload.get("status")
        if status == "accepted":
            _require_fields(
                payload,
                ("server_device_id", "session_token", "heartbeat_interval_ms"),
                "payload",
            )

    if message_type == MessageType.AUTH_LOGIN_RESPONSE:
        if payload.get("status") == "ok":
            _require_fields(payload, ("user_id", "session"), "payload")
            _assert_mapping(payload.get("session"), "payload.session")

    if message_type == MessageType.SYNC_PUSH_REQUEST:
        events = payload.get("events")
        if not isinstance(events, list):
            raise ProtocolValidationError("payload.events must be an array")
        for index, event in enumerate(events):
            _assert_mapping(event, f"payload.events[{index}]")
            _require_fields(
                event,
                ("event_id", "event_type", "event_ts_ms", "payload"),
                f"payload.events[{index}]",
            )

    if message_type == MessageType.SYNC_PULL_RESPONSE:
        events = payload.get("events")
        if not isinstance(events, list):
            raise ProtocolValidationError("payload.events must be an array")

    if message_type == MessageType.ERROR_RESPONSE:
        error_payload = payload.get("error")
        _assert_mapping(error_payload, "payload.error")
        typed_error_payload = cast(Mapping[str, Any], error_payload)
        _require_fields(typed_error_payload, ("code", "message", "retryable"), "payload.error")
        code_value = typed_error_payload.get("code")
        allowed_codes = {item.value for item in ErrorCode}
        if code_value not in allowed_codes:
            raise ProtocolValidationError(
                f"payload.error.code must be one of: {', '.join(sorted(allowed_codes))}"
            )


def _require_fields(payload: Mapping[str, Any], fields: tuple[str, ...], scope: str) -> None:
    missing = [field for field in fields if field not in payload]
    if missing:
        raise ProtocolValidationError(f"{scope} missing required fields: {', '.join(missing)}")


def _assert_mapping(value: Any, scope: str) -> None:
    if not isinstance(value, Mapping):
        raise ProtocolValidationError(f"{scope} must be an object")
