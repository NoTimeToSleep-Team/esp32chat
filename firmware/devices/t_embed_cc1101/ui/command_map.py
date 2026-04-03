from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TEmbedClientCommand:
    command_id: str
    method: str
    path_template: str
    description: str


T_EMBED_CC1101_CLIENT_COMMANDS: tuple[TEmbedClientCommand, ...] = (
    TEmbedClientCommand(
        command_id="auth_login",
        method="POST",
        path_template="/auth/login",
        description="Secure login",
    ),
    TEmbedClientCommand(
        command_id="auth_logout",
        method="POST",
        path_template="/auth/logout",
        description="Session revoke",
    ),
    TEmbedClientCommand(
        command_id="auth_session",
        method="GET",
        path_template="/auth/session/{session_token}",
        description="Session validation",
    ),
    TEmbedClientCommand(
        command_id="chat_list",
        method="GET",
        path_template="/chat/api/chats",
        description="List chats",
    ),
    TEmbedClientCommand(
        command_id="chat_history",
        method="GET",
        path_template="/chat/api/chats/{chat_id}/messages",
        description="Load chat history",
    ),
    TEmbedClientCommand(
        command_id="chat_send",
        method="POST",
        path_template="/chat/api/chats/{chat_id}/messages",
        description="Send text message",
    ),
    TEmbedClientCommand(
        command_id="blog_list",
        method="GET",
        path_template="/blog/api/posts",
        description="List blog posts",
    ),
    TEmbedClientCommand(
        command_id="blog_get",
        method="GET",
        path_template="/blog/api/posts/{post_id}",
        description="Read blog post",
    ),
)


def command_path_set() -> set[str]:
    return {item.path_template for item in T_EMBED_CC1101_CLIENT_COMMANDS}
