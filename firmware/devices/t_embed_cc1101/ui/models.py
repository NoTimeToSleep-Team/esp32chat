from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TemplateEntry:
    template_id: str
    title: str
    body_text: str


@dataclass(frozen=True)
class TemplateCatalog:
    count: int
    items: tuple[TemplateEntry, ...]


@dataclass(frozen=True)
class BufferEntry:
    buffer_key: str
    chat_id: int
    body_text: str
    client_message_id: str
    queued_at_ms: int
    attempts: int
    last_error: str


@dataclass(frozen=True)
class BufferSnapshot:
    count: int
    items: tuple[BufferEntry, ...]


@dataclass(frozen=True)
class SendOutcome:
    status: str
    client_message_id: str
    message_id: int | None
    buffered_count: int


@dataclass(frozen=True)
class BufferFlushResult:
    attempted: int
    sent: int
    remaining: int
