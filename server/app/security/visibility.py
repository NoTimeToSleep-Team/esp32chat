"""Single source of truth for chat history/message visibility.

The same rules must be used by list/search, replies, reactions, forwards,
polls and attachment downloads.  Keeping this in one place prevents a hidden
history from leaking through a side channel.
"""
from __future__ import annotations

import sqlite3
from typing import Mapping


def _value(row: Mapping[str, object] | sqlite3.Row, key: str, default: object = None) -> object:
    try:
        return row[key]
    except (KeyError, IndexError):
        return default


def _as_bool(row: Mapping[str, object] | sqlite3.Row, key: str, default: bool = False) -> bool:
    value = _value(row, key, None)
    if value is None:
        return default
    return bool(int(value))


def _as_int(row: Mapping[str, object] | sqlite3.Row, key: str, default: int = 0) -> int:
    value = _value(row, key, None)
    if value is None:
        return default
    return int(value)


def read_floor_for_chat(
    connection: sqlite3.Connection,
    *,
    chat_row: Mapping[str, object] | sqlite3.Row,
    user_id: int,
) -> int | None:
    """Return the oldest message timestamp the user may read.

    ``None`` means the user must not read this chat's message history at all.
    A returned ``0`` means the whole history is visible (subject to per-user
    cleared_at, which is folded into the result).
    """
    role_row = connection.execute(
        "SELECT role FROM users WHERE id = ?",
        (int(user_id),),
    ).fetchone()
    role = str(role_row["role"]) if role_row is not None else ""
    is_platform_moderator = role in {"admin", "moderator"}

    kind = str(_value(chat_row, "kind", "") or "")
    history_visible = _as_bool(chat_row, "history_visible", True)
    is_public = _as_bool(chat_row, "is_public", False)
    chat_id = _as_int(chat_row, "id", 0)

    member = connection.execute(
        "SELECT joined_at_ms, cleared_at_ms FROM chat_members WHERE chat_id = ? AND user_id = ?",
        (chat_id, int(user_id)),
    ).fetchone()

    if member is None:
        if kind == "common":
            return 0
        if is_platform_moderator:
            return 0
        if is_public and history_visible:
            return 0
        return None

    floor = 0
    if not history_visible:
        floor = max(floor, _as_int(member, "joined_at_ms", 0))
    cleared_at_ms = _as_int(member, "cleared_at_ms", 0)
    if cleared_at_ms:
        floor = max(floor, cleared_at_ms)
    return floor


def message_is_readable(
    connection: sqlite3.Connection,
    *,
    message_row: Mapping[str, object] | sqlite3.Row,
    chat_row: Mapping[str, object] | sqlite3.Row,
    user_id: int,
) -> bool:
    floor = read_floor_for_chat(connection, chat_row=chat_row, user_id=user_id)
    if floor is None:
        return False
    return _as_int(message_row, "created_at_ms", 0) >= floor
