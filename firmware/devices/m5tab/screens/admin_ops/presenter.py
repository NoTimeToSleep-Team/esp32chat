from __future__ import annotations

from typing import Any, Mapping

from .models import (
    AdminModeStateView,
    BlogPostView,
    BlogPostsScreenData,
    RfidCardView,
    RfidCardsScreenData,
    SupportMessageView,
    SupportTicketView,
    SupportTicketsScreenData,
)


def build_support_tickets_screen(
    payload: Mapping[str, Any],
    *,
    status_filter: str | None,
) -> SupportTicketsScreenData:
    _require_ok(payload)
    items_raw = payload.get("items")
    if not isinstance(items_raw, list):
        items_raw = []

    items: list[SupportTicketView] = []
    for item in items_raw:
        if not isinstance(item, Mapping):
            continue
        items.append(parse_support_ticket(item))

    count = _to_int(payload.get("count"), default=len(items))
    return SupportTicketsScreenData(count=count, status_filter=status_filter, items=tuple(items))


def build_blog_posts_screen(payload: Mapping[str, Any]) -> BlogPostsScreenData:
    _require_ok(payload)
    items_raw = payload.get("items")
    if not isinstance(items_raw, list):
        items_raw = []

    items: list[BlogPostView] = []
    for item in items_raw:
        if not isinstance(item, Mapping):
            continue
        items.append(parse_blog_post(item))

    count = _to_int(payload.get("count"), default=len(items))
    return BlogPostsScreenData(count=count, items=tuple(items))


def build_rfid_cards_screen(payload: Mapping[str, Any]) -> RfidCardsScreenData:
    _require_ok(payload)
    items_raw = payload.get("items")
    if not isinstance(items_raw, list):
        items_raw = []

    items: list[RfidCardView] = []
    for item in items_raw:
        if not isinstance(item, Mapping):
            continue
        items.append(parse_rfid_card(item))

    count = _to_int(payload.get("count"), default=len(items))
    return RfidCardsScreenData(count=count, items=tuple(items))


def parse_support_ticket(payload: Mapping[str, Any]) -> SupportTicketView:
    return SupportTicketView(
        ticket_id=_to_int(payload.get("ticket_id"), default=0),
        user_id=_to_int(payload.get("user_id"), default=0),
        title=_to_str(payload.get("title"), default=""),
        status=_to_str(payload.get("status"), default="unknown"),
        last_message_at_ms=_to_int(payload.get("last_message_at_ms"), default=0),
    )


def parse_support_message(payload: Mapping[str, Any]) -> SupportMessageView:
    return SupportMessageView(
        message_id=_to_int(payload.get("message_id"), default=0),
        ticket_id=_to_int(payload.get("ticket_id"), default=0),
        author_user_id=_to_int(payload.get("author_user_id"), default=0),
        body_text=_to_str(payload.get("body_text"), default=""),
        created_at_ms=_to_int(payload.get("created_at_ms"), default=0),
    )


def parse_blog_post(payload: Mapping[str, Any]) -> BlogPostView:
    return BlogPostView(
        post_id=_to_int(payload.get("post_id"), default=0),
        title=_to_str(payload.get("title"), default=""),
        author_user_id=_to_int(payload.get("author_user_id"), default=0),
        published_at_ms=_to_int(payload.get("published_at_ms"), default=0),
    )


def parse_rfid_card(payload: Mapping[str, Any]) -> RfidCardView:
    return RfidCardView(
        card_id=_to_int(payload.get("card_id"), default=0),
        uid_mask=_to_str(payload.get("uid_mask"), default=""),
        card_label=_to_str(payload.get("card_label"), default=""),
        is_active=_to_bool(payload.get("is_active"), default=False),
    )


def parse_mode_state(payload: Mapping[str, Any]) -> AdminModeStateView:
    _require_ok(payload)
    sequence_raw = payload.get("safe_sequence")
    sequence: list[str] = []
    if isinstance(sequence_raw, list):
        for item in sequence_raw:
            if isinstance(item, str):
                sequence.append(item)

    return AdminModeStateView(
        access_mode=_to_str(payload.get("access_mode"), default="unknown"),
        required_hold_seconds=_to_int(payload.get("required_hold_seconds"), default=5),
        safe_sequence=tuple(sequence),
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


def _to_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    return default
