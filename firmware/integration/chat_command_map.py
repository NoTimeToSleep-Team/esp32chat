from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IntegrationChatCommand:
    command_id: str
    method: str
    path_template: str
    description: str


CHAT_INTEGRATION_COMMANDS: tuple[IntegrationChatCommand, ...] = (
    IntegrationChatCommand(
        command_id="auth_login",
        method="POST",
        path_template="/auth/login",
        description="Authenticate web and device actors",
    ),
    IntegrationChatCommand(
        command_id="chat_list",
        method="GET",
        path_template="/chat/api/chats",
        description="Resolve shared chat for e2e scenario",
    ),
    IntegrationChatCommand(
        command_id="chat_send",
        method="POST",
        path_template="/chat/api/chats/{chat_id}/messages",
        description="Send message through device flow",
    ),
    IntegrationChatCommand(
        command_id="chat_history",
        method="GET",
        path_template="/chat/api/chats/{chat_id}/messages",
        description="Read chat history through both flows",
    ),
)


CHAT_INTEGRATION_WEBSOCKET_PATHS: tuple[str, ...] = (
    "/realtime/chat/{chat_id}",
)


def command_path_set() -> set[str]:
    paths = {item.path_template for item in CHAT_INTEGRATION_COMMANDS}
    return paths | set(CHAT_INTEGRATION_WEBSOCKET_PATHS)
