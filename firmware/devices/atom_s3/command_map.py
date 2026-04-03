from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AllowedCommand:
    command_id: str
    method: str
    path: str
    description: str


ATOM_ALLOWED_COMMANDS: tuple[AllowedCommand, ...] = (
    AllowedCommand(
        command_id="health_check",
        method="GET",
        path="/health",
        description="Read health status",
    ),
    AllowedCommand(
        command_id="health_readiness",
        method="GET",
        path="/health/ready",
        description="Read readiness status",
    ),
    AllowedCommand(
        command_id="ops_state",
        method="GET",
        path="/ops/api/state",
        description="Read runtime state",
    ),
    AllowedCommand(
        command_id="ops_set_degraded_mode",
        method="POST",
        path="/ops/api/degraded-mode",
        description="Toggle maintenance/degraded mode",
    ),
    AllowedCommand(
        command_id="ops_shutdown_dry_run",
        method="POST",
        path="/ops/api/shutdown/dry-run",
        description="Run safe shutdown dry-run sequence",
    ),
    AllowedCommand(
        command_id="ops_incident_create",
        method="POST",
        path="/ops/api/incidents",
        description="Record operator-visible incident",
    ),
    AllowedCommand(
        command_id="ops_incident_list",
        method="GET",
        path="/ops/api/incidents",
        description="Read incidents for status panel",
    ),
)


def command_path_set() -> set[str]:
    return {item.path for item in ATOM_ALLOWED_COMMANDS}
