from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AllowedCommand:
    command_id: str
    method: str
    path: str
    description: str


M5STAMP_ALLOWED_COMMANDS: tuple[AllowedCommand, ...] = (
    AllowedCommand(
        command_id="health_check",
        method="GET",
        path="/health",
        description="Read-only server liveness check",
    ),
    AllowedCommand(
        command_id="health_readiness",
        method="GET",
        path="/health/ready",
        description="Read-only readiness check for diagnostics overlays",
    ),
)


def command_path_set() -> set[str]:
    return {item.path for item in M5STAMP_ALLOWED_COMMANDS}
