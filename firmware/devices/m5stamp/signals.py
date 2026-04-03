from __future__ import annotations

from dataclasses import dataclass

from .models import EmergencySeverity, HeartbeatStatus


@dataclass(frozen=True)
class SignalInfo:
    signal_id: str
    severity: EmergencySeverity
    description: str


_SIGNAL_CATALOG: dict[str, SignalInfo] = {
    "power_warning": SignalInfo(
        signal_id="power_warning",
        severity=EmergencySeverity.WARNING,
        description="Power rail is outside normal expected envelope",
    ),
    "temp_warning": SignalInfo(
        signal_id="temp_warning",
        severity=EmergencySeverity.WARNING,
        description="Board temperature exceeded warning threshold",
    ),
    "network_loss": SignalInfo(
        signal_id="network_loss",
        severity=EmergencySeverity.WARNING,
        description="Primary network channel is unavailable",
    ),
    "watchdog_timeout": SignalInfo(
        signal_id="watchdog_timeout",
        severity=EmergencySeverity.CRITICAL,
        description="Node watchdog timeout detected",
    ),
    "safe_shutdown_requested": SignalInfo(
        signal_id="safe_shutdown_requested",
        severity=EmergencySeverity.CRITICAL,
        description="Service node received safe shutdown request",
    ),
    "internal_fault": SignalInfo(
        signal_id="internal_fault",
        severity=EmergencySeverity.CRITICAL,
        description="Internal fault detected in service node",
    ),
}


class EmergencySignal(str):
    POWER_WARNING = "power_warning"
    TEMP_WARNING = "temp_warning"
    NETWORK_LOSS = "network_loss"
    WATCHDOG_TIMEOUT = "watchdog_timeout"
    SAFE_SHUTDOWN_REQUESTED = "safe_shutdown_requested"
    INTERNAL_FAULT = "internal_fault"


class EmergencySignalRegistry:
    def __init__(self) -> None:
        self._active: dict[str, str | None] = {}

    def activate(self, *, signal_id: str, reason: str | None = None) -> None:
        key = signal_id.strip()
        if key not in _SIGNAL_CATALOG:
            raise ValueError(f"unknown signal_id: {signal_id}")
        self._active[key] = (reason or "").strip() or None

    def clear(self, *, signal_id: str) -> None:
        key = signal_id.strip()
        self._active.pop(key, None)

    def clear_all(self) -> None:
        self._active.clear()

    def active_signals(self) -> tuple[str, ...]:
        return tuple(sorted(self._active.keys()))

    def reason_for(self, signal_id: str) -> str | None:
        return self._active.get(signal_id)

    def highest_severity(self, *, network_ok: bool) -> EmergencySeverity:
        severity = EmergencySeverity.NONE
        keys = set(self._active.keys())
        if not network_ok:
            keys.add(EmergencySignal.NETWORK_LOSS)

        for key in keys:
            info = _SIGNAL_CATALOG.get(key)
            if info is None:
                continue
            if info.severity == EmergencySeverity.CRITICAL:
                return EmergencySeverity.CRITICAL
            if info.severity == EmergencySeverity.WARNING:
                severity = EmergencySeverity.WARNING
        return severity

    def heartbeat_status(self, *, network_ok: bool) -> HeartbeatStatus:
        severity = self.highest_severity(network_ok=network_ok)
        if severity == EmergencySeverity.CRITICAL:
            return HeartbeatStatus.HOLD_STATE
        if severity == EmergencySeverity.WARNING:
            return HeartbeatStatus.DEGRADED
        return HeartbeatStatus.OK
