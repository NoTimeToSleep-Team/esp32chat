from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AdminUserView:
    user_id: int
    login: str
    role: str
    status: str
    phone: str | None
    registration_device_id: str | None
    block_reason: str | None
    blocked_until_ms: int | None
    device_blacklisted: bool


@dataclass(frozen=True)
class DeviceBlacklistView:
    device_id: str
    reason: str | None
    blocked_by_user_id: int
    created_at_ms: int
    updated_at_ms: int


@dataclass(frozen=True)
class UserDeleteResult:
    deleted_user_id: int
    deleted_login: str


@dataclass(frozen=True)
class UsersScreenData:
    count: int
    status_filter: str | None
    items: tuple[AdminUserView, ...]
