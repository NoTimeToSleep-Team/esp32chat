from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.models.media import MediaAttachment


class SupportTicketStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class SupportTicketKind(str, Enum):
    SUPPORT = "support"
    REPORT = "report"
    BUG = "bug"
    IDEA = "idea"
    OTHER = "other"


@dataclass(frozen=True)
class SupportTicket:
    ticket_id: int
    user_id: int
    title: str
    status: SupportTicketStatus
    created_at_ms: int
    updated_at_ms: int
    last_message_at_ms: int
    kind: SupportTicketKind = SupportTicketKind.SUPPORT
    target_user_id: int | None = None


@dataclass(frozen=True)
class SupportMessage:
    message_id: int
    ticket_id: int
    author_user_id: int
    body_text: str
    created_at_ms: int
    attachments: tuple[MediaAttachment, ...] = ()


@dataclass(frozen=True)
class SupportTicketDraft:
    title: str
    body_text: str
    attachment_ids: tuple[int, ...] = ()
    kind: SupportTicketKind = SupportTicketKind.SUPPORT
    target_user_id: int | None = None

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("Support ticket title must not be empty")
        if not self.body_text.strip() and not self.attachment_ids:
            raise ValueError("Support ticket message or attachment must be provided")


@dataclass(frozen=True)
class SupportMessageDraft:
    body_text: str
    attachment_ids: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not self.body_text.strip() and not self.attachment_ids:
            raise ValueError("Support message text or attachment must be provided")
