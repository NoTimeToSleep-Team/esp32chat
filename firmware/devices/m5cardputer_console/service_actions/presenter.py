from __future__ import annotations

from typing import Any, Mapping

from .models import ConsoleServiceSnapshot


def build_service_snapshot(
    *,
    health_payload: Mapping[str, Any],
    readiness_payload: Mapping[str, Any],
    mode_payload: Mapping[str, Any],
    limits_payload: Mapping[str, Any],
) -> ConsoleServiceSnapshot:
    _require_status(health_payload, allowed={"ok"})
    _require_status(readiness_payload)
    _require_status(mode_payload, allowed={"ok"})
    _require_status(limits_payload, allowed={"ok"})

    limits = limits_payload.get("limits")
    if not isinstance(limits, Mapping):
        limits = {}

    return ConsoleServiceSnapshot(
        health_status=_to_str(health_payload.get("status"), default="unknown"),
        readiness_status=_to_str(readiness_payload.get("status"), default="unknown"),
        access_mode=_to_str(mode_payload.get("access_mode"), default="unknown"),
        limits_role=_to_str(limits.get("role"), default="unknown"),
        max_custom_chats=_to_int(limits.get("max_custom_chats"), default=0),
        remaining_custom_chats=_to_int(limits.get("remaining_custom_chats"), default=0),
        can_create_custom_chats=_to_bool(limits.get("can_create_custom_chats"), default=False),
    )


def _require_status(payload: Mapping[str, Any], allowed: set[str] | None = None) -> None:
    status = payload.get("status")
    if not isinstance(status, str) or not status:
        raise RuntimeError(f"unexpected payload status: {status}")
    if allowed is not None and status not in allowed:
        raise RuntimeError(f"unexpected payload status: {status}")


def _to_str(value: Any, *, default: str) -> str:
    if isinstance(value, str):
        return value
    return default


def _to_int(value: Any, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return default


def _to_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    return default
