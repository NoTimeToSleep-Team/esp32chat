from __future__ import annotations

from typing import Any, Mapping

from .models import AdminUserView, DeviceBlacklistView, UserDeleteResult, UsersScreenData


def build_users_screen(payload: Mapping[str, Any], *, status_filter: str | None) -> UsersScreenData:
    _require_ok(payload)
    items_raw = payload.get("items")
    if not isinstance(items_raw, list):
        items_raw = []

    items: list[AdminUserView] = []
    for item in items_raw:
        if not isinstance(item, Mapping):
            continue
        items.append(parse_user(item))

    count = _to_int(payload.get("count"), default=len(items))
    return UsersScreenData(
        count=count,
        status_filter=status_filter,
        items=tuple(items),
    )


def parse_user(payload: Mapping[str, Any]) -> AdminUserView:
    return AdminUserView(
        user_id=_to_int(payload.get("user_id"), default=0),
        login=_to_str(payload.get("login"), default=""),
        role=_to_str(payload.get("role"), default="unknown"),
        status=_to_str(payload.get("status"), default="unknown"),
        phone=_to_optional_str(payload.get("phone")),
        registration_device_id=_to_optional_str(payload.get("registration_device_id")),
        block_reason=_to_optional_str(payload.get("block_reason")),
        blocked_until_ms=_to_optional_int(payload.get("blocked_until_ms")),
        device_blacklisted=_to_bool(payload.get("device_blacklisted"), default=False),
    )


def parse_blacklist_entry(payload: Mapping[str, Any]) -> DeviceBlacklistView:
    return DeviceBlacklistView(
        device_id=_to_str(payload.get("device_id"), default=""),
        reason=_to_optional_str(payload.get("reason")),
        blocked_by_user_id=_to_int(payload.get("blocked_by_user_id"), default=0),
        created_at_ms=_to_int(payload.get("created_at_ms"), default=0),
        updated_at_ms=_to_int(payload.get("updated_at_ms"), default=0),
    )


def parse_delete_result(payload: Mapping[str, Any]) -> UserDeleteResult:
    _require_ok(payload)
    return UserDeleteResult(
        deleted_user_id=_to_int(payload.get("deleted_user_id"), default=0),
        deleted_login=_to_str(payload.get("deleted_login"), default=""),
    )


def _require_ok(payload: Mapping[str, Any]) -> None:
    if payload.get("status") != "ok":
        raise RuntimeError(f"unexpected payload status: {payload.get('status')}")


def _to_int(value: Any, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return default


def _to_optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _to_str(value: Any, *, default: str) -> str:
    if isinstance(value, str):
        return value
    return default


def _to_optional_str(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    return None


def _to_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    return default
