"""Shared avatar payload decoding (used by account and chat photos)."""
from __future__ import annotations

import base64
import binascii

from app.models import AvatarImage


class AvatarPayloadError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def decode_avatar_payload(
    *,
    image_base64: str,
    image_mime_type: str | None,
) -> AvatarImage:
    raw = (image_base64 or "").strip()
    mime_from_data_url: str | None = None

    if raw.startswith("data:") and "," in raw:
        header, payload = raw.split(",", 1)
        if ";base64" not in header:
            raise AvatarPayloadError(
                "invalid_avatar_payload",
                "Avatar data URL must be base64-encoded",
            )
        mime_from_data_url = header[5:].split(";", 1)[0].strip().lower()
        raw = payload

    raw = "".join(raw.split())
    mime = (mime_from_data_url or (image_mime_type or "")).strip().lower()

    if not mime:
        raise AvatarPayloadError(
            "invalid_avatar_payload",
            "Avatar mime type is required",
        )

    try:
        content = base64.b64decode(raw, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise AvatarPayloadError(
            "invalid_avatar_payload",
            "Avatar base64 payload is invalid",
        ) from exc

    if not content:
        raise AvatarPayloadError(
            "invalid_avatar_payload",
            "Avatar image is empty",
        )

    try:
        return AvatarImage(content=content, mime_type=mime)
    except ValueError as exc:
        raise AvatarPayloadError("invalid_avatar_payload", str(exc)) from exc
