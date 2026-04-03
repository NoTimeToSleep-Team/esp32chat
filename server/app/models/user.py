from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class UserRole(str, Enum):
    GUEST = "guest"
    USER = "user"
    ADMIN = "admin"


class UserStatus(str, Enum):
    ACTIVE = "active"
    BLOCKED = "blocked"
    BANNED = "banned"


class AccessMode(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


class ClientKind(str, Enum):
    WEB = "web"
    DEVICE = "device"


@dataclass(frozen=True)
class UserConstraints:
    max_user_custom_chats: int = 5
    guest_allowed_only_in_open_mode: bool = True
    guest_allowed_only_on_web: bool = True


@dataclass(frozen=True)
class User:
    login: str
    role: UserRole
    status: UserStatus = UserStatus.ACTIVE
    password_hash: str | None = None
    user_id: int | None = None

    def __post_init__(self) -> None:
        if not self.login.strip():
            raise ValueError("User login must not be empty")

        if self.role in {UserRole.USER, UserRole.ADMIN} and not self.password_hash:
            raise ValueError("Registered users must have password_hash")

    @property
    def is_active(self) -> bool:
        return self.status == UserStatus.ACTIVE

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN

    @property
    def is_guest(self) -> bool:
        return self.role == UserRole.GUEST

    def can_authenticate(
        self,
        *,
        client_kind: ClientKind,
        access_mode: AccessMode,
        constraints: UserConstraints | None = None,
    ) -> bool:
        rules = constraints or UserConstraints()

        if self.status in {UserStatus.BLOCKED, UserStatus.BANNED}:
            return False

        if self.role != UserRole.GUEST:
            return True

        if rules.guest_allowed_only_in_open_mode and access_mode != AccessMode.OPEN:
            return False

        if rules.guest_allowed_only_on_web and client_kind != ClientKind.WEB:
            return False

        return True

    def can_create_custom_chat(
        self,
        *,
        existing_custom_chat_count: int,
        constraints: UserConstraints | None = None,
    ) -> bool:
        rules = constraints or UserConstraints()

        if self.status != UserStatus.ACTIVE:
            return False

        if self.role == UserRole.ADMIN:
            return True

        if self.role == UserRole.GUEST:
            return False

        return existing_custom_chat_count < rules.max_user_custom_chats

    def can_access_admin_features(self) -> bool:
        return self.status == UserStatus.ACTIVE and self.role == UserRole.ADMIN
