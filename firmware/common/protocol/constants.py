from __future__ import annotations

from enum import Enum


PROTOCOL_VERSION = "1.0"
SUPPORTED_PROTOCOL_MAJOR = 1


class EndpointKind(str, Enum):
    SERVER = "server"
    DEVICE = "device"
    WEB_CLIENT = "web_client"
    SERVICE = "service"


class MessageType(str, Enum):
    DEVICE_REGISTER_REQUEST = "device.register.request"
    DEVICE_REGISTER_RESPONSE = "device.register.response"
    DEVICE_HEARTBEAT = "device.heartbeat"
    TELEMETRY_SNAPSHOT = "telemetry.snapshot"

    AUTH_LOGIN_REQUEST = "auth.login.request"
    AUTH_LOGIN_RESPONSE = "auth.login.response"

    CHAT_SEND_REQUEST = "chat.send.request"
    CHAT_SEND_RESPONSE = "chat.send.response"
    CHAT_MESSAGE_EVENT = "chat.message.event"

    SYNC_PUSH_REQUEST = "sync.push.request"
    SYNC_PUSH_RESPONSE = "sync.push.response"
    SYNC_PULL_REQUEST = "sync.pull.request"
    SYNC_PULL_RESPONSE = "sync.pull.response"
    SYNC_ACK = "sync.ack"

    ERROR_RESPONSE = "error.response"


class ErrorCode(str, Enum):
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    INVALID_PAYLOAD = "invalid_payload"
    UNSUPPORTED_MESSAGE_TYPE = "unsupported_message_type"
    RATE_LIMITED = "rate_limited"
    CONFLICT = "conflict"
    RESYNC_REQUIRED = "resync_required"
    INTERNAL_ERROR = "internal_error"


MUTATING_MESSAGE_TYPES = frozenset(
    {
        MessageType.DEVICE_REGISTER_REQUEST,
        MessageType.AUTH_LOGIN_REQUEST,
        MessageType.CHAT_SEND_REQUEST,
        MessageType.SYNC_PUSH_REQUEST,
    }
)
