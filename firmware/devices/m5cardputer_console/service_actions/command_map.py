from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceActionCommand:
    command_id: str
    method: str
    path_template: str
    description: str


M5CARDPUTER_CONSOLE_SERVICE_COMMANDS: tuple[ServiceActionCommand, ...] = (
    ServiceActionCommand(
        command_id="health",
        method="GET",
        path_template="/health",
        description="Read service health",
    ),
    ServiceActionCommand(
        command_id="readiness",
        method="GET",
        path_template="/health/ready",
        description="Read service readiness",
    ),
    ServiceActionCommand(
        command_id="mode",
        method="GET",
        path_template="/mode",
        description="Read current access mode",
    ),
    ServiceActionCommand(
        command_id="account_limits",
        method="GET",
        path_template="/account/api/limits",
        description="Read account limits for service shortcuts",
    ),
)


def service_command_path_set() -> set[str]:
    return {item.path_template for item in M5CARDPUTER_CONSOLE_SERVICE_COMMANDS}
