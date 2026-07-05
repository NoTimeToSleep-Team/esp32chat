from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    LIMITED = "limited"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    AUTHENTICATED = "authenticated"
    DEGRADED = "degraded"


class FlipperScreen(str, Enum):
    HOME = "home"
    CHAT = "chat"
    BLOG = "blog"


@dataclass(frozen=True)
class CapabilitySnapshot:
    wifi_dev_board_attached: bool
    network_mode_enabled: bool
    mode: str
    reason: str
    detected_at_ms: int


@dataclass(frozen=True)
class FlipperSession:
    user_id: int
    login: str
    role: str
    user_status: str
    access_mode: str
    token: str
    created_at_ms: int
    expires_at_ms: int


@dataclass(frozen=True)
class FlipperShellState:
    connection_state: ConnectionState
    connected: bool
    capability: CapabilitySnapshot | None
    session: FlipperSession | None
    active_screen: FlipperScreen
    last_sync_ms: int
    last_error_code: str | None


def disconnected_state() -> FlipperShellState:
    return FlipperShellState(
        connection_state=ConnectionState.DISCONNECTED,
        connected=False,
        capability=None,
        session=None,
        active_screen=FlipperScreen.HOME,
        last_sync_ms=0,
        last_error_code=None,
    )
