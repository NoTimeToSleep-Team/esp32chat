from __future__ import annotations

from typing import Any, Mapping

from .models import ChatHistoryScreenData, ChatListScreenData, ChatMessageView, ChatRoomView, ChatSendResult


def build_chat_list(payload: Mapping[str, Any]) -> ChatListScreenData:
    _require_ok(payload)
    items_raw = payload.get("items")
    if not isinstance(items_raw, list):
        items_raw = []

    items: list[ChatRoomView] = []
    for item in items_raw:
        if not isinstance(item, Mapping):
            continue
        items.append(parse_chat_room(item))

    count = _to_int(payload.get("count"), default=len(items))
    return ChatListScreenData(count=count, items=tuple(items))


def build_chat_history(payload: Mapping[str, Any], *, chat_id: int) -> ChatHistoryScreenData:
    _require_ok(payload)
    items_raw = payload.get("items")
    if not isinstance(items_raw, list):
        items_raw = []

    items: list[ChatMessageView] = []
    for item in items_raw:
        if not isinstance(item, Mapping):
            continue
        items.append(parse_message(item))

    count = _to_int(payload.get("count"), default=len(items))
    return ChatHistoryScreenData(chat_id=chat_id, count=count, items=tuple(items))


def parse_send_result(payload: Mapping[str, Any]) -> ChatSendResult:
    _require_ok(payload)
    message_payload = payload.get("message")
    if not isinstance(message_payload, Mapping):
        raise RuntimeError("send_message payload.message must be object")

    return ChatSendResult(
        message=parse_message(message_payload),
        delivered_to=_to_int(payload.get("delivered_to"), default=0),
    )


def parse_chat_room(payload: Mapping[str, Any]) -> ChatRoomView:
    return ChatRoomView(
        chat_id=_to_int(payload.get("chat_id"), default=0),
        kind=_to_str(payload.get("kind"), default="unknown"),
        title=_to_str(payload.get("title"), default=""),
        is_private=_to_bool(payload.get("is_private"), default=False),
        updated_at_ms=_to_int(payload.get("updated_at_ms"), default=0),
    )


def parse_message(payload: Mapping[str, Any]) -> ChatMessageView:
    return ChatMessageView(
        message_id=_to_int(payload.get("message_id"), default=0),
        chat_id=_to_int(payload.get("chat_id"), default=0),
        author_user_id=_to_int(payload.get("author_user_id"), default=0),
        body_text=_to_str(payload.get("body_text"), default=""),
        client_message_id=_to_optional_str(payload.get("client_message_id")),
        created_at_ms=_to_int(payload.get("created_at_ms"), default=0),
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


def _to_optional_str(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    return None


def _to_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    return default
