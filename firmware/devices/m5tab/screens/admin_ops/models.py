from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SupportTicketView:
    ticket_id: int
    user_id: int
    title: str
    status: str
    last_message_at_ms: int


@dataclass(frozen=True)
class SupportMessageView:
    message_id: int
    ticket_id: int
    author_user_id: int
    body_text: str
    created_at_ms: int


@dataclass(frozen=True)
class BlogPostView:
    post_id: int
    title: str
    author_user_id: int
    published_at_ms: int


@dataclass(frozen=True)
class RfidCardView:
    card_id: int
    uid_mask: str
    card_label: str
    is_active: bool


@dataclass(frozen=True)
class AdminModeStateView:
    access_mode: str
    required_hold_seconds: int
    safe_sequence: tuple[str, ...]


@dataclass(frozen=True)
class SupportTicketsScreenData:
    count: int
    status_filter: str | None
    items: tuple[SupportTicketView, ...]


@dataclass(frozen=True)
class BlogPostsScreenData:
    count: int
    items: tuple[BlogPostView, ...]


@dataclass(frozen=True)
class RfidCardsScreenData:
    count: int
    items: tuple[RfidCardView, ...]
