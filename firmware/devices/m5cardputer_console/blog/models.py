from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BlogPostView:
    post_id: int
    title: str
    body_text: str
    author_user_id: int
    published_at_ms: int


@dataclass(frozen=True)
class BlogPostsScreenData:
    count: int
    items: tuple[BlogPostView, ...]
