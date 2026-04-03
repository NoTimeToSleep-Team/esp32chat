from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class HeartbeatStatus(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    HOLD_STATE = "hold_state"


@dataclass(frozen=True)
class PowerSample:
    vin_mv: int
    current_ma: int

    def to_payload(self) -> dict[str, int]:
        return {
            "vin_mv": self.vin_mv,
            "current_ma": self.current_ma,
        }


@dataclass(frozen=True)
class ThermalSample:
    board_c: float
    ambient_c: float

    def to_payload(self) -> dict[str, float]:
        return {
            "board_c": self.board_c,
            "ambient_c": self.ambient_c,
        }


@dataclass(frozen=True)
class ServiceFlags:
    watchdog_ok: bool
    safe_shutdown_ready: bool
    network_ok: bool

    def to_payload(self) -> dict[str, bool]:
        return {
            "watchdog_ok": self.watchdog_ok,
            "safe_shutdown_ready": self.safe_shutdown_ready,
        }


@dataclass(frozen=True)
class TelemetrySnapshot:
    power: PowerSample
    temperature: ThermalSample
    service_flags: ServiceFlags

    def to_payload(self) -> dict[str, object]:
        return {
            "power": self.power.to_payload(),
            "temperature": self.temperature.to_payload(),
            "service_flags": self.service_flags.to_payload(),
        }


@dataclass(frozen=True)
class DiagnosticsReport:
    watchdog_ok: bool
    watchdog_missed_count: int
    queue_depth: int
    last_error_code: str | None
    last_error_message: str | None
    network_ok: bool
    generated_at_ms: int

    def to_payload(self) -> dict[str, object]:
        return {
            "watchdog_ok": self.watchdog_ok,
            "watchdog_missed_count": self.watchdog_missed_count,
            "queue_depth": self.queue_depth,
            "last_error_code": self.last_error_code,
            "last_error_message": self.last_error_message,
            "network_ok": self.network_ok,
            "generated_at_ms": self.generated_at_ms,
        }
