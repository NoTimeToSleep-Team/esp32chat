from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChatRoomView:
    chat_id: int
    kind: str
    title: str
    is_private: bool
    updated_at_ms: int


@dataclass(frozen=True)
class ChatMessageView:
    message_id: int
    chat_id: int
    author_user_id: int
    body_text: str
    client_message_id: str | None
    created_at_ms: int


@dataclass(frozen=True)
class ChatListScreenData:
    count: int
    items: tuple[ChatRoomView, ...]


@dataclass(frozen=True)
class ChatHistoryScreenData:
    chat_id: int
    count: int
    items: tuple[ChatMessageView, ...]


@dataclass(frozen=True)
class ChatSendResult:
    message: ChatMessageView
    delivered_to: int
