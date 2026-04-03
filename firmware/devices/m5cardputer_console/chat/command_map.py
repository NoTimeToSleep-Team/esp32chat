from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConsoleChatCommand:
    command_id: str
    method: str
    path_template: str
    description: str


M5CARDPUTER_CONSOLE_CHAT_COMMANDS: tuple[ConsoleChatCommand, ...] = (
    ConsoleChatCommand(
        command_id="chat_list",
        method="GET",
        path_template="/chat/api/chats",
        description="Read chat list for console",
    ),
    ConsoleChatCommand(
        command_id="chat_history",
        method="GET",
        path_template="/chat/api/chats/{chat_id}/messages",
        description="Read messages from selected chat",
    ),
    ConsoleChatCommand(
        command_id="chat_send",
        method="POST",
        path_template="/chat/api/chats/{chat_id}/messages",
        description="Send text message to chat",
    ),
)


def chat_command_path_set() -> set[str]:
    return {item.path_template for item in M5CARDPUTER_CONSOLE_CHAT_COMMANDS}
