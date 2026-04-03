from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConsoleServiceSnapshot:
    health_status: str
    readiness_status: str
    access_mode: str
    limits_role: str
    max_custom_chats: int
    remaining_custom_chats: int
    can_create_custom_chats: bool
