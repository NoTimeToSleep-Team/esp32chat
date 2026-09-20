from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.models.media import MediaAttachment


class ChatKind(str, Enum):
    COMMON = "common"
    CUSTOM = "custom"


class ChatMemberRole(str, Enum):
    OWNER = "owner"
    MEMBER = "member"


@dataclass(frozen=True)
class ChatRoom:
    chat_id: int
    kind: ChatKind
    title: str
    description: str | None
    owner_user_id: int | None
    is_private: bool
    avatar_url: str | None
    has_room_code: bool
    created_at_ms: int
    updated_at_ms: int


@dataclass(frozen=True)
class ChatMember:
    chat_id: int
    user_id: int
    role: ChatMemberRole
    joined_at_ms: int


@dataclass(frozen=True)
class ChatMessage:
    message_id: int
    chat_id: int
    author_user_id: int
    body_text: str
    client_message_id: str | None
    created_at_ms: int
    edited_at_ms: int | None
    attachments: tuple[MediaAttachment, ...] = ()
    author_login: str | None = None
    author_avatar_emoji: str | None = None


@dataclass(frozen=True)
class ChatDraft:
    title: str
    description: str | None = None

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("Chat title must not be empty")


@dataclass(frozen=True)
class MessageDraft:
    body_text: str
    client_message_id: str | None = None
    attachment_ids: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not self.body_text.strip() and not self.attachment_ids:
            raise ValueError("Message text or attachment must be provided")
