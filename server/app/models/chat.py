from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.models.media import MediaAttachment


class ChatKind(str, Enum):
    COMMON = "common"
    CUSTOM = "custom"


class ChatType(str, Enum):
    DM = "dm"
    GROUP = "group"
    CHANNEL = "channel"


class ChatMemberRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    SUBSCRIBER = "subscriber"


#: Permission flags stored as a JSON object in chat_members.permissions.
CHAT_PERMISSIONS: tuple[str, ...] = (
    "change_info",
    "delete_messages",
    "invite_users",
    "pin_messages",
    "manage_invites",
    "restrict_members",
)


def default_admin_permissions() -> dict[str, bool]:
    return {name: True for name in CHAT_PERMISSIONS}


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
    avatar_path: str | None = None
    chat_type: ChatType = ChatType.GROUP
    username: str | None = None
    is_public: bool = False
    slow_mode_seconds: int = 0
    pinned_message_id: int | None = None
    history_visible: bool = True


@dataclass(frozen=True)
class ChatMember:
    chat_id: int
    user_id: int
    role: ChatMemberRole
    joined_at_ms: int
    permissions: str | None = None
    is_muted: bool = False
    is_archived: bool = False
    is_pinned: bool = False
    cleared_at_ms: int | None = None
    last_read_message_id: int | None = None


@dataclass(frozen=True)
class ChatInvite:
    invite_id: int
    chat_id: int
    code: str
    created_by: int | None
    created_at_ms: int
    expires_at_ms: int | None
    max_uses: int | None
    uses: int
    requires_approval: bool


@dataclass(frozen=True)
class ChatJoinRequest:
    chat_id: int
    user_id: int
    status: str
    created_at_ms: int
    decided_by: int | None = None
    decided_at_ms: int | None = None


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
    chat_type: ChatType = ChatType.GROUP
    username: str | None = None
    is_public: bool = False
    history_visible: bool = True

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
