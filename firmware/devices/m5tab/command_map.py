from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TelemetryCommand:
    command_id: str
    method: str
    path: str
    requires_session: bool
    description: str


M5TAB_TELEMETRY_COMMANDS: tuple[TelemetryCommand, ...] = (
    TelemetryCommand(
        command_id="health_check",
        method="GET",
        path="/health",
        requires_session=False,
        description="Read service health telemetry",
    ),
    TelemetryCommand(
        command_id="readiness_check",
        method="GET",
        path="/health/ready",
        requires_session=False,
        description="Read service readiness telemetry",
    ),
    TelemetryCommand(
        command_id="mode_read",
        method="GET",
        path="/mode",
        requires_session=False,
        description="Read global access mode",
    ),
    TelemetryCommand(
        command_id="ops_runtime_read",
        method="GET",
        path="/ops/api/state",
        requires_session=True,
        description="Read runtime degraded mode state (admin session)",
    ),
    TelemetryCommand(
        command_id="ops_incidents_read",
        method="GET",
        path="/ops/api/incidents",
        requires_session=True,
        description="Read active incidents count (admin session)",
    ),
)


def command_path_set() -> set[str]:
    return {item.path for item in M5TAB_TELEMETRY_COMMANDS}
