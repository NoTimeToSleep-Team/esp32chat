from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class QuickAction(str, Enum):
    MAINTENANCE_MODE_ON = "maintenance_mode_on"
    MAINTENANCE_MODE_OFF = "maintenance_mode_off"
    SAFE_SHUTDOWN_DRY_RUN = "safe_shutdown_dry_run"
    SIGNAL_NETWORK_RESET = "signal_network_reset"


class SystemStatus(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    HOLD_STATE = "hold_state"


class StatusPattern(str, Enum):
    STEADY_GREEN = "steady_green"
    BLINK_YELLOW = "blink_yellow"
    BLINK_RED_FAST = "blink_red_fast"


@dataclass(frozen=True)
class StatusPanel:
    system_status: SystemStatus
    pattern: StatusPattern
    runtime_degraded_mode: bool
    active_alert_count: int
    health_status: str
    generated_at_ms: int

    def to_payload(self) -> dict[str, object]:
        return {
            "system_status": self.system_status.value,
            "pattern": self.pattern.value,
            "runtime_degraded_mode": self.runtime_degraded_mode,
            "active_alert_count": self.active_alert_count,
            "health_status": self.health_status,
            "generated_at_ms": self.generated_at_ms,
        }
