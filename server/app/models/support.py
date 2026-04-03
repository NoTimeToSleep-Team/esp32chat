from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SupportTicketStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


@dataclass(frozen=True)
class SupportTicket:
    ticket_id: int
    user_id: int
    title: str
    status: SupportTicketStatus
    created_at_ms: int
    updated_at_ms: int
    last_message_at_ms: int


@dataclass(frozen=True)
class SupportMessage:
    message_id: int
    ticket_id: int
    author_user_id: int
    body_text: str
    created_at_ms: int


@dataclass(frozen=True)
class SupportTicketDraft:
    title: str
    body_text: str

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("Support ticket title must not be empty")
        if not self.body_text.strip():
            raise ValueError("Support ticket message must not be empty")


@dataclass(frozen=True)
class SupportMessageDraft:
    body_text: str

    def __post_init__(self) -> None:
        if not self.body_text.strip():
            raise ValueError("Support message text must not be empty")
