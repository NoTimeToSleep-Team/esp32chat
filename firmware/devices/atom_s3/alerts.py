from __future__ import annotations

from dataclasses import dataclass

from .models import AlertSeverity


@dataclass(frozen=True)
class AlertRecord:
    alert_id: str
    severity: AlertSeverity
    message: str
    created_at_ms: int
    updated_at_ms: int


class AlertRegistry:
    def __init__(self) -> None:
        self._alerts: dict[str, AlertRecord] = {}

    def upsert(
        self,
        *,
        alert_id: str,
        severity: AlertSeverity,
        message: str,
        now_ms: int,
    ) -> AlertRecord:
        normalized_id = alert_id.strip()
        if not normalized_id:
            raise ValueError("alert_id must not be empty")

        normalized_message = message.strip() or "no details"
        existing = self._alerts.get(normalized_id)
        if existing is None:
            record = AlertRecord(
                alert_id=normalized_id,
                severity=severity,
                message=normalized_message,
                created_at_ms=now_ms,
                updated_at_ms=now_ms,
            )
        else:
            record = AlertRecord(
                alert_id=existing.alert_id,
                severity=severity,
                message=normalized_message,
                created_at_ms=existing.created_at_ms,
                updated_at_ms=now_ms,
            )

        self._alerts[normalized_id] = record
        return record

    def clear(self, *, alert_id: str) -> None:
        self._alerts.pop(alert_id.strip(), None)

    def clear_all(self) -> None:
        self._alerts.clear()

    def active(self) -> tuple[AlertRecord, ...]:
        return tuple(sorted(self._alerts.values(), key=lambda item: item.alert_id))

    def highest_severity(self) -> AlertSeverity | None:
        highest: AlertSeverity | None = None
        for record in self._alerts.values():
            if record.severity == AlertSeverity.CRITICAL:
                return AlertSeverity.CRITICAL
            if record.severity == AlertSeverity.WARNING:
                highest = AlertSeverity.WARNING
            elif highest is None:
                highest = AlertSeverity.INFO
        return highest
