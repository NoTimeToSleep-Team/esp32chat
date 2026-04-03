from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    AUTHENTICATED = "authenticated"
    DEGRADED = "degraded"


class CompactScreen(str, Enum):
    HOME = "home"
    CHAT = "chat"
    BLOG = "blog"


@dataclass(frozen=True)
class CompactSession:
    user_id: int
    login: str
    role: str
    user_status: str
    access_mode: str
    token: str
    created_at_ms: int
    expires_at_ms: int


@dataclass(frozen=True)
class CompactShellState:
    connection_state: ConnectionState
    connected: bool
    session: CompactSession | None
    active_screen: CompactScreen
    last_sync_ms: int
    last_error_code: str | None


def disconnected_state() -> CompactShellState:
    return CompactShellState(
        connection_state=ConnectionState.DISCONNECTED,
        connected=False,
        session=None,
        active_screen=CompactScreen.HOME,
        last_sync_ms=0,
        last_error_code=None,
    )
