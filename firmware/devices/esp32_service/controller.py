from __future__ import annotations

from typing import Any

from firmware.common.protocol.models import Envelope
from firmware.common.queue import LocalEventQueue, QueueEventState

from .config import Esp32ServiceConfig
from .diagnostics import DiagnosticsCollector
from .models import DiagnosticsReport, HeartbeatStatus, ServiceFlags, TelemetrySnapshot
from .server_api import ServerOpsGateway
from .telemetry import TelemetryEnvelopeFactory
from .watchdog import WatchdogSupervisor


class Esp32ServiceController:
    def __init__(
        self,
        *,
        config: Esp32ServiceConfig,
        gateway: ServerOpsGateway,
        queue: LocalEventQueue | None = None,
        watchdog: WatchdogSupervisor | None = None,
        diagnostics: DiagnosticsCollector | None = None,
        telemetry_factory: TelemetryEnvelopeFactory | None = None,
    ) -> None:
        self._config = config
        self._gateway = gateway
        self._queue = queue or LocalEventQueue()
        self._watchdog = watchdog or WatchdogSupervisor(timeout_ms=config.watchdog_timeout_ms)
        self._diagnostics = diagnostics or DiagnosticsCollector()
        self._telemetry = telemetry_factory or TelemetryEnvelopeFactory(config)

    @property
    def queue(self) -> LocalEventQueue:
        return self._queue

    @property
    def watchdog(self) -> WatchdogSupervisor:
        return self._watchdog

    def register_boot(self, *, now_ms: int) -> Envelope:
        return self._telemetry.register_request(sent_at_ms=now_ms)

    def heartbeat(self, *, now_ms: int, uptime_ms: int, network_ok: bool) -> Envelope:
        watchdog_ok = self._watchdog.evaluate(now_ms)
        status = HeartbeatStatus.OK
        if not network_ok or not watchdog_ok:
            status = HeartbeatStatus.DEGRADED

        queue_depth = self._queue_depth()
        metrics = {
            "queue_depth": queue_depth,
            "watchdog_missed": self._watchdog.missed_count,
            "network_ok": 1 if network_ok else 0,
        }
        if not watchdog_ok:
            self._diagnostics.record_error(
                code="watchdog_timeout",
                message="watchdog did not receive feed in timeout window",
                occurred_at_ms=now_ms,
            )
        return self._telemetry.heartbeat(
            sent_at_ms=now_ms,
            uptime_ms=uptime_ms,
            queue_depth=queue_depth,
            status=status,
            metrics=metrics,
        )

    def telemetry_snapshot(self, *, now_ms: int, snapshot: TelemetrySnapshot) -> Envelope:
        if not snapshot.service_flags.network_ok:
            self._diagnostics.record_error(
                code="network_degraded",
                message="network flag indicates degraded state",
                occurred_at_ms=now_ms,
            )
        return self._telemetry.telemetry_snapshot(sent_at_ms=now_ms, snapshot=snapshot)

    def diagnostics_report(self, *, now_ms: int, network_ok: bool) -> DiagnosticsReport:
        watchdog_ok = self._watchdog.is_healthy(now_ms)
        return self._diagnostics.build_report(
            watchdog_ok=watchdog_ok,
            watchdog_missed_count=self._watchdog.missed_count,
            queue_depth=self._queue_depth(),
            network_ok=network_ok,
            generated_at_ms=now_ms,
        )

    def feed_watchdog(self, *, now_ms: int) -> None:
        self._watchdog.feed(now_ms)

    def server_health(self) -> dict[str, Any]:
        return self._gateway.health()

    def runtime_state(self) -> dict[str, Any]:
        token = self._config.require_ops_session()
        return self._gateway.runtime_state(session_token=token)

    def set_degraded_mode(self, *, enabled: bool, reason: str) -> dict[str, Any]:
        token = self._config.require_ops_session()
        return self._gateway.set_degraded_mode(
            session_token=token,
            enabled=enabled,
            reason=reason,
        )

    def safe_shutdown_dry_run(self, *, reason: str) -> dict[str, Any]:
        token = self._config.require_ops_session()
        return self._gateway.shutdown_dry_run(session_token=token, reason=reason)

    def _queue_depth(self) -> int:
        counts = self._queue.count_by_state()
        return counts[QueueEventState.PENDING.value] + counts[QueueEventState.SENT.value]
