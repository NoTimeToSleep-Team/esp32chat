from __future__ import annotations

from typing import Any

from .alerts import AlertRegistry
from .config import AtomS3Config
from .models import AlertSeverity, QuickAction, StatusPanel, StatusPattern, SystemStatus
from .server_api import OpsGateway


class AtomS3Controller:
    def __init__(
        self,
        *,
        config: AtomS3Config,
        gateway: OpsGateway,
        alerts: AlertRegistry | None = None,
    ) -> None:
        self._config = config
        self._gateway = gateway
        self._alerts = alerts or AlertRegistry()

    def status_panel(self, *, now_ms: int) -> StatusPanel:
        health = self._gateway.health()
        runtime = self._gateway.runtime_state(session_token=self._config.require_ops_session())

        health_status = str(health.get("status", "unknown"))
        runtime_payload = runtime.get("runtime") if isinstance(runtime, dict) else None
        runtime_degraded = False
        if isinstance(runtime_payload, dict):
            runtime_degraded = bool(runtime_payload.get("degraded_mode", False))

        active = self._alerts.active()
        highest = self._alerts.highest_severity()

        system_status = SystemStatus.OK
        pattern = StatusPattern.STEADY_GREEN

        if health_status != "ok":
            system_status = SystemStatus.DEGRADED
            pattern = StatusPattern.BLINK_YELLOW

        if runtime_degraded:
            system_status = SystemStatus.DEGRADED
            pattern = StatusPattern.BLINK_YELLOW

        if highest == AlertSeverity.WARNING:
            system_status = SystemStatus.DEGRADED
            pattern = StatusPattern.BLINK_YELLOW
        elif highest == AlertSeverity.CRITICAL:
            system_status = SystemStatus.HOLD_STATE
            pattern = StatusPattern.BLINK_RED_FAST

        return StatusPanel(
            system_status=system_status,
            pattern=pattern,
            runtime_degraded_mode=runtime_degraded,
            active_alert_count=len(active),
            health_status=health_status,
            generated_at_ms=now_ms,
        )

    def raise_alert(
        self,
        *,
        alert_id: str,
        severity: AlertSeverity,
        message: str,
        now_ms: int,
    ) -> dict[str, Any]:
        record = self._alerts.upsert(
            alert_id=alert_id,
            severity=severity,
            message=message,
            now_ms=now_ms,
        )
        return self._gateway.create_incident(
            session_token=self._config.require_ops_session(),
            severity=severity,
            title=f"atom_s3:{record.alert_id}",
            source="atom_s3",
            details={
                "message": record.message,
                "updated_at_ms": record.updated_at_ms,
            },
        )

    def clear_alert(self, *, alert_id: str) -> None:
        self._alerts.clear(alert_id=alert_id)

    def execute_quick_action(
        self,
        *,
        action: QuickAction,
        reason: str,
        now_ms: int,
    ) -> dict[str, Any]:
        token = self._config.require_ops_session()

        if action == QuickAction.MAINTENANCE_MODE_ON:
            return self._gateway.set_degraded_mode(
                session_token=token,
                enabled=True,
                reason=reason,
            )

        if action == QuickAction.MAINTENANCE_MODE_OFF:
            return self._gateway.set_degraded_mode(
                session_token=token,
                enabled=False,
                reason=reason,
            )

        if action == QuickAction.SAFE_SHUTDOWN_DRY_RUN:
            return self._gateway.shutdown_dry_run(session_token=token, reason=reason)

        if action == QuickAction.SIGNAL_NETWORK_RESET:
            self._alerts.upsert(
                alert_id="network_reset_requested",
                severity=AlertSeverity.WARNING,
                message=reason,
                now_ms=now_ms,
            )
            return self._gateway.create_incident(
                session_token=token,
                severity=AlertSeverity.WARNING,
                title="atom_s3:network_reset_requested",
                source="atom_s3",
                details={
                    "reason": reason,
                    "requested_at_ms": now_ms,
                },
            )

        raise RuntimeError(f"unsupported quick action: {action.value}")

    def list_incidents(self, *, limit: int = 20) -> dict[str, Any]:
        return self._gateway.list_incidents(
            session_token=self._config.require_ops_session(),
            limit=limit,
        )

    def readiness(self) -> dict[str, Any]:
        return self._gateway.readiness()
