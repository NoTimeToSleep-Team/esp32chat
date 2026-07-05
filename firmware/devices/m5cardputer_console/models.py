from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    AUTHENTICATED = "authenticated"
    DEGRADED = "degraded"


class NavigationScreen(str, Enum):
    HOME = "home"
    CHAT = "chat"
    BLOG = "blog"
    SERVICE = "service"


@dataclass(frozen=True)
class ConsoleSession:
    user_id: int
    login: str
    role: str
    user_status: str
    access_mode: str
    token: str
    created_at_ms: int
    expires_at_ms: int


@dataclass(frozen=True)
class ConsoleShellState:
    connection_state: ConnectionState
    connected: bool
    session: ConsoleSession | None
    active_screen: NavigationScreen
    last_sync_ms: int
    last_error_code: str | None


def disconnected_state() -> ConsoleShellState:
    return ConsoleShellState(
        connection_state=ConnectionState.DISCONNECTED,
        connected=False,
        session=None,
        active_screen=NavigationScreen.HOME,
        last_sync_ms=0,
        last_error_code=None,
    )
