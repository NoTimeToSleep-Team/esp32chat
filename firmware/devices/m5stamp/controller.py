from __future__ import annotations

from typing import Any

from firmware.common.protocol.models import Envelope

from .config import M5StampConfig
from .heartbeat import M5StampEnvelopeFactory
from .indicator import IndicatorController
from .models import HeartbeatStatus, IndicatorState, TelemetrySnapshotData
from .server_api import HealthGateway
from .signals import EmergencySignalRegistry
from .telemetry_hooks import TelemetryHooksRegistry


class M5StampController:
    def __init__(
        self,
        *,
        config: M5StampConfig,
        gateway: HealthGateway,
        signal_registry: EmergencySignalRegistry | None = None,
        telemetry_hooks: TelemetryHooksRegistry | None = None,
        indicator: IndicatorController | None = None,
        envelope_factory: M5StampEnvelopeFactory | None = None,
    ) -> None:
        self._config = config
        self._gateway = gateway
        self._signals = signal_registry or EmergencySignalRegistry()
        self._hooks = telemetry_hooks or TelemetryHooksRegistry()
        self._indicator = indicator or IndicatorController()
        self._factory = envelope_factory or M5StampEnvelopeFactory(config)

    @property
    def indicator_state(self) -> IndicatorState:
        return self._indicator.state

    def register_hook(self, *, key: str, provider: Any) -> None:
        self._hooks.register(key=key, provider=provider)

    def activate_signal(self, *, signal_id: str, reason: str | None = None) -> None:
        self._signals.activate(signal_id=signal_id, reason=reason)

    def clear_signal(self, *, signal_id: str) -> None:
        self._signals.clear(signal_id=signal_id)

    def active_signals(self) -> tuple[str, ...]:
        return self._signals.active_signals()

    def register_boot(self, *, now_ms: int) -> Envelope:
        return self._factory.register_request(now_ms=now_ms)

    def heartbeat(
        self,
        *,
        now_ms: int,
        uptime_ms: int,
        queue_depth: int,
        network_ok: bool,
    ) -> Envelope:
        status = self._signals.heartbeat_status(network_ok=network_ok)
        indicator_state = self._indicator.apply_status(status=status, network_ok=network_ok)
        return self._factory.heartbeat(
            now_ms=now_ms,
            uptime_ms=uptime_ms,
            queue_depth=queue_depth,
            status=status,
            indicator_state=indicator_state,
            active_signals=self._signals.active_signals(),
            network_ok=network_ok,
        )

    def telemetry_snapshot(self, *, now_ms: int, network_ok: bool) -> Envelope:
        status = self._signals.heartbeat_status(network_ok=network_ok)
        snapshot = self._hooks.snapshot_data(
            watchdog_ok=status != HeartbeatStatus.HOLD_STATE,
            safe_shutdown_ready=status != HeartbeatStatus.HOLD_STATE,
        )
        return self._factory.telemetry_snapshot(
            now_ms=now_ms,
            snapshot_data=snapshot,
            active_signals=self._signals.active_signals(),
        )

    def preview_snapshot_data(self, *, network_ok: bool) -> TelemetrySnapshotData:
        status = self._signals.heartbeat_status(network_ok=network_ok)
        return self._hooks.snapshot_data(
            watchdog_ok=status != HeartbeatStatus.HOLD_STATE,
            safe_shutdown_ready=status != HeartbeatStatus.HOLD_STATE,
        )

    def server_health(self) -> dict[str, Any]:
        return self._gateway.health()

    def server_readiness(self) -> dict[str, Any]:
        return self._gateway.readiness()
