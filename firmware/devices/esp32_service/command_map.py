from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ServerCommand:
    command_id: str
    method: str
    path: str
    requires_session: bool
    description: str


ESP32_SERVICE_COMMANDS: tuple[ServerCommand, ...] = (
    ServerCommand(
        command_id="health_check",
        method="GET",
        path="/health",
        requires_session=False,
        description="Fetch server health and runtime state snapshot",
    ),
    ServerCommand(
        command_id="ops_runtime_state",
        method="GET",
        path="/ops/api/state",
        requires_session=True,
        description="Read ops runtime state including degraded mode flag",
    ),
    ServerCommand(
        command_id="ops_set_degraded_mode",
        method="POST",
        path="/ops/api/degraded-mode",
        requires_session=True,
        description="Toggle degraded mode with explicit reason",
    ),
    ServerCommand(
        command_id="ops_shutdown_dry_run",
        method="POST",
        path="/ops/api/shutdown/dry-run",
        requires_session=True,
        description="Trigger safe shutdown orchestration dry-run",
    ),
)


def command_path_set() -> set[str]:
    return {item.path for item in ESP32_SERVICE_COMMANDS}
