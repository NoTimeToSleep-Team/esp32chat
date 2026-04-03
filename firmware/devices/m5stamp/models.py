from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class HeartbeatStatus(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    HOLD_STATE = "hold_state"


class EmergencySeverity(str, Enum):
    NONE = "none"
    WARNING = "warning"
    CRITICAL = "critical"


class IndicatorPattern(str, Enum):
    STEADY_GREEN = "steady_green"
    BLINK_YELLOW = "blink_yellow"
    BLINK_RED_FAST = "blink_red_fast"
    BLINK_BLUE_SLOW = "blink_blue_slow"


@dataclass(frozen=True)
class IndicatorState:
    pattern: IndicatorPattern
    brightness_pct: int
    blink_interval_ms: int | None

    def to_payload(self) -> dict[str, object]:
        return {
            "pattern": self.pattern.value,
            "brightness_pct": self.brightness_pct,
            "blink_interval_ms": self.blink_interval_ms,
        }


@dataclass(frozen=True)
class TelemetrySnapshotData:
    vin_mv: int
    current_ma: int
    board_c: float
    ambient_c: float
    watchdog_ok: bool
    safe_shutdown_ready: bool

    def to_payload(self) -> dict[str, object]:
        return {
            "power": {
                "vin_mv": self.vin_mv,
                "current_ma": self.current_ma,
            },
            "temperature": {
                "board_c": self.board_c,
                "ambient_c": self.ambient_c,
            },
            "service_flags": {
                "watchdog_ok": self.watchdog_ok,
                "safe_shutdown_ready": self.safe_shutdown_ready,
            },
        }
