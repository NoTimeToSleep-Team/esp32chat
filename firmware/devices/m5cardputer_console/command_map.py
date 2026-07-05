from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConsoleCommand:
    command_id: str
    method: str
    path_template: str
    requires_session: bool
    description: str


M5CARDPUTER_CONSOLE_COMMANDS: tuple[ConsoleCommand, ...] = (
    ConsoleCommand(
        command_id="auth_login",
        method="POST",
        path_template="/auth/login",
        requires_session=False,
        description="Secure login for device client",
    ),
    ConsoleCommand(
        command_id="auth_logout",
        method="POST",
        path_template="/auth/logout",
        requires_session=True,
        description="Revoke active device session",
    ),
    ConsoleCommand(
        command_id="auth_session",
        method="GET",
        path_template="/auth/session/{session_token}",
        requires_session=True,
        description="Validate active device session",
    ),
    ConsoleCommand(
        command_id="mode_read",
        method="GET",
        path_template="/mode",
        requires_session=False,
        description="Read current global access mode",
    ),
)


def command_path_set() -> set[str]:
    return {item.path_template for item in M5CARDPUTER_CONSOLE_COMMANDS}
