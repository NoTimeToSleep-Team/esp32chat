from __future__ import annotations

from dataclasses import dataclass

from app.models.user import UserRole, UserStatus


@dataclass(frozen=True)
class AccountProfile:
    user_id: int
    login: str
    role: UserRole
    status: UserStatus
    phone: str | None
    display_name: str | None
    profile_bio: str | None
    avatar_path: str | None
    avatar_updated_at_ms: int | None


@dataclass(frozen=True)
class AccountProfileUpdate:
    display_name: str | None = None
    profile_bio: str | None = None

    def __post_init__(self) -> None:
        if self.display_name is not None and len(self.display_name.strip()) > 128:
            raise ValueError("display_name must be <= 128 chars")
        if self.profile_bio is not None and len(self.profile_bio.strip()) > 1024:
            raise ValueError("profile_bio must be <= 1024 chars")


@dataclass(frozen=True)
class AvatarImage:
    content: bytes
    mime_type: str

    def __post_init__(self) -> None:
        if not self.content:
            raise ValueError("Avatar content must not be empty")


@dataclass(frozen=True)
class AccountLimits:
    role: UserRole
    max_custom_chats: int | None
    current_custom_chats: int
    remaining_custom_chats: int | None
    can_create_custom_chats: bool
