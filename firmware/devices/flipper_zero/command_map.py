from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FlipperCommand:
    command_id: str
    method: str
    path_template: str
    requires_session: bool
    requires_network: bool
    description: str


FLIPPER_ZERO_COMMANDS: tuple[FlipperCommand, ...] = (
    FlipperCommand(
        command_id="auth_login",
        method="POST",
        path_template="/auth/login",
        requires_session=False,
        requires_network=True,
        description="Secure login for Flipper client",
    ),
    FlipperCommand(
        command_id="auth_logout",
        method="POST",
        path_template="/auth/logout",
        requires_session=True,
        requires_network=True,
        description="Revoke active session",
    ),
    FlipperCommand(
        command_id="auth_session",
        method="GET",
        path_template="/auth/session/{session_token}",
        requires_session=True,
        requires_network=True,
        description="Validate active session",
    ),
    FlipperCommand(
        command_id="mode_read",
        method="GET",
        path_template="/mode",
        requires_session=False,
        requires_network=True,
        description="Read global access mode",
    ),
    FlipperCommand(
        command_id="health_ping",
        method="GET",
        path_template="/health",
        requires_session=False,
        requires_network=True,
        description="Probe network route availability",
    ),
)


def command_path_set() -> set[str]:
    return {item.path_template for item in FLIPPER_ZERO_COMMANDS}
