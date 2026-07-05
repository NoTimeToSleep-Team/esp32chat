from __future__ import annotations

from .errors import ProtocolValidationError


def format_idempotency_key(sender_id: str, boot_id: str, counter: int) -> str:
    normalized_sender = sender_id.strip()
    normalized_boot = boot_id.strip()
    if not normalized_sender or not normalized_boot:
        raise ProtocolValidationError("sender_id and boot_id must not be empty")
    if counter < 0:
        raise ProtocolValidationError("counter must be >= 0")

    key = f"{normalized_sender}:{normalized_boot}:{counter:06d}"
    _assert_ascii(key, "idempotency_key")
    return key


def is_valid_idempotency_key(value: str | None) -> bool:
    if value is None:
        return False
    key = value.strip()
    if not key:
        return False
    parts = key.split(":")
    if len(parts) != 3:
        return False
    sender, boot_id, counter = parts
    if not sender or not boot_id or not counter:
        return False
    if not counter.isdigit():
        return False
    try:
        key.encode("ascii")
    except UnicodeEncodeError:
        return False
    return True


def _assert_ascii(value: str, field_name: str) -> None:
    try:
        value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ProtocolValidationError(f"{field_name} must use ASCII characters") from exc
