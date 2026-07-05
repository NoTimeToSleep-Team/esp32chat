from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HandheldSession:
    user_id: int
    login: str
    role: str
    status: str
    access_mode: str
    session_token: str
    created_at_ms: int
    expires_at_ms: int
