from __future__ import annotations

from dataclasses import dataclass

from app.models.media import MediaAttachment


@dataclass(frozen=True)
class BlogPost:
    post_id: int
    title: str
    body_text: str
    author_user_id: int
    published_at_ms: int
    updated_at_ms: int
    attachments: tuple[MediaAttachment, ...] = ()


@dataclass(frozen=True)
class BlogPostDraft:
    title: str
    body_text: str
    attachment_ids: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("Post title must not be empty")
        if not self.body_text.strip():
            raise ValueError("Post body must not be empty")
