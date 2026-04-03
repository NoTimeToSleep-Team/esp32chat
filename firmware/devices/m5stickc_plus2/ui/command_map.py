from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompactClientCommand:
    command_id: str
    method: str
    path_template: str
    description: str


M5STICKC_PLUS2_CLIENT_COMMANDS: tuple[CompactClientCommand, ...] = (
    CompactClientCommand(
        command_id="auth_login",
        method="POST",
        path_template="/auth/login",
        description="Secure login",
    ),
    CompactClientCommand(
        command_id="auth_logout",
        method="POST",
        path_template="/auth/logout",
        description="Session revoke",
    ),
    CompactClientCommand(
        command_id="auth_session",
        method="GET",
        path_template="/auth/session/{session_token}",
        description="Session validation",
    ),
    CompactClientCommand(
        command_id="chat_list",
        method="GET",
        path_template="/chat/api/chats",
        description="List chats",
    ),
    CompactClientCommand(
        command_id="chat_history",
        method="GET",
        path_template="/chat/api/chats/{chat_id}/messages",
        description="Load chat history",
    ),
    CompactClientCommand(
        command_id="chat_send",
        method="POST",
        path_template="/chat/api/chats/{chat_id}/messages",
        description="Send text message",
    ),
    CompactClientCommand(
        command_id="blog_list",
        method="GET",
        path_template="/blog/api/posts",
        description="List blog posts",
    ),
    CompactClientCommand(
        command_id="blog_get",
        method="GET",
        path_template="/blog/api/posts/{post_id}",
        description="Read blog post",
    ),
)


def command_path_set() -> set[str]:
    return {item.path_template for item in M5STICKC_PLUS2_CLIENT_COMMANDS}
