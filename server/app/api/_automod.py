"""Helpers to run auto-moderation after message changes."""
from __future__ import annotations

import logging

LOGGER = logging.getLogger("lc.auto_moderation")


def moderate_message(request_or_app, message) -> None:
    """Scan a message and file a report if needed. Never raises."""
    if message is None:
        return
    app = getattr(request_or_app, "app", None) or request_or_app
    service = getattr(getattr(app, "state", None), "auto_moderation", None)
    if service is None:
        return
    try:
        service.check_message(message)
    except Exception:  # noqa: BLE001 - moderation must never break messaging
        LOGGER.exception("auto-moderation failed for message %s", getattr(message, "message_id", "?"))
