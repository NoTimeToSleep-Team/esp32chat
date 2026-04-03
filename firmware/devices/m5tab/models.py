from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DEGRADED = "degraded"


@dataclass(frozen=True)
class ShellState:
    connection_state: ConnectionState
    connected: bool
    last_sync_ms: int | None
    last_error: str | None


@dataclass(frozen=True)
class InfoScreenData:
    health_status: str
    readiness_status: str
    profile: str
    uptime_ms: int
    access_mode: str
    runtime_degraded_mode: bool
    data_layer_initialized: bool
    applied_migrations: int
    active_incidents_count: int | None
    generated_at_ms: int

    def to_payload(self) -> dict[str, object]:
        return {
            "health_status": self.health_status,
            "readiness_status": self.readiness_status,
            "profile": self.profile,
            "uptime_ms": self.uptime_ms,
            "access_mode": self.access_mode,
            "runtime_degraded_mode": self.runtime_degraded_mode,
            "data_layer_initialized": self.data_layer_initialized,
            "applied_migrations": self.applied_migrations,
            "active_incidents_count": self.active_incidents_count,
            "generated_at_ms": self.generated_at_ms,
        }
