from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from app.models import ChatKind, UserRole, UserStatus


@dataclass(frozen=True)
class ChatLimitDecision:
    allowed: bool
    status_code: int
    reason_code: str | None
    reason_message: str | None
    current_count: int
    limit: int | None


class ChatLimitsService:
    def __init__(self, *, max_user_custom_chats: int = 5) -> None:
        self._max_user_custom_chats = max_user_custom_chats

    def evaluate_custom_chat_creation(
        self,
        connection: sqlite3.Connection,
        *,
        user_id: int,
    ) -> ChatLimitDecision:
        row = connection.execute(
            "SELECT id, role, status FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

        if row is None:
            return ChatLimitDecision(
                allowed=False,
                status_code=404,
                reason_code="user_not_found",
                reason_message="User not found",
                current_count=0,
                limit=self._max_user_custom_chats,
            )

        status = str(row["status"])
        if status != UserStatus.ACTIVE.value:
            return ChatLimitDecision(
                allowed=False,
                status_code=403,
                reason_code="user_inactive",
                reason_message="User is blocked or banned",
                current_count=0,
                limit=self._max_user_custom_chats,
            )

        role = str(row["role"])
        if role == UserRole.GUEST.value:
            return ChatLimitDecision(
                allowed=False,
                status_code=403,
                reason_code="guest_forbidden",
                reason_message="Guest cannot create custom chats",
                current_count=0,
                limit=self._max_user_custom_chats,
            )

        if role == UserRole.ADMIN.value:
            count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM chats WHERE kind = ? AND owner_user_id = ?",
                    (ChatKind.CUSTOM.value, user_id),
                ).fetchone()[0]
            )
            return ChatLimitDecision(
                allowed=True,
                status_code=200,
                reason_code=None,
                reason_message=None,
                current_count=count,
                limit=None,
            )

        count = int(
            connection.execute(
                "SELECT COUNT(*) FROM chats WHERE kind = ? AND owner_user_id = ?",
                (ChatKind.CUSTOM.value, user_id),
            ).fetchone()[0]
        )

        if count >= self._max_user_custom_chats:
            return ChatLimitDecision(
                allowed=False,
                status_code=409,
                reason_code="custom_chat_limit_reached",
                reason_message=(
                    f"Custom chat limit reached for user ({count}/{self._max_user_custom_chats})"
                ),
                current_count=count,
                limit=self._max_user_custom_chats,
            )

        return ChatLimitDecision(
            allowed=True,
            status_code=200,
            reason_code=None,
            reason_message=None,
            current_count=count,
            limit=self._max_user_custom_chats,
        )
