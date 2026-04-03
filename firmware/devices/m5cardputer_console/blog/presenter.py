from __future__ import annotations

from typing import Any, Mapping

from .models import BlogPostsScreenData, BlogPostView


def build_blog_posts(payload: Mapping[str, Any]) -> BlogPostsScreenData:
    _require_ok(payload)
    items_raw = payload.get("items")
    if not isinstance(items_raw, list):
        items_raw = []

    items: list[BlogPostView] = []
    for item in items_raw:
        if not isinstance(item, Mapping):
            continue
        items.append(parse_post(item))

    count = _to_int(payload.get("count"), default=len(items))
    return BlogPostsScreenData(count=count, items=tuple(items))


def parse_post_payload(payload: Mapping[str, Any]) -> BlogPostView:
    _require_ok(payload)
    post_payload = payload.get("post")
    if not isinstance(post_payload, Mapping):
        raise RuntimeError("blog payload.post must be object")
    return parse_post(post_payload)


def parse_post(payload: Mapping[str, Any]) -> BlogPostView:
    return BlogPostView(
        post_id=_to_int(payload.get("post_id"), default=0),
        title=_to_str(payload.get("title"), default=""),
        body_text=_to_str(payload.get("body_text"), default=""),
        author_user_id=_to_int(payload.get("author_user_id"), default=0),
        published_at_ms=_to_int(payload.get("published_at_ms"), default=0),
    )


def _require_ok(payload: Mapping[str, Any]) -> None:
    if payload.get("status") != "ok":
        raise RuntimeError(f"unexpected payload status: {payload.get('status')}")


def _to_int(value: Any, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return default


def _to_str(value: Any, *, default: str) -> str:
    if isinstance(value, str):
        return value
    return default
