from __future__ import annotations

from dataclasses import dataclass

from app.models.user import UserRole, UserStatus


@dataclass(frozen=True)
class AdminUserRecord:
    user_id: int
    login: str
    role: UserRole
    status: UserStatus
    phone: str | None
    registration_device_id: str | None
    created_at_ms: int
    updated_at_ms: int
    block_reason: str | None
    blocked_until_ms: int | None
    restriction_updated_by_user_id: int | None
    restriction_updated_at_ms: int | None
    device_blacklisted: bool


@dataclass(frozen=True)
class DeviceBlacklistEntry:
    device_id: str
    reason: str | None
    blocked_by_user_id: int
    created_at_ms: int
    updated_at_ms: int
