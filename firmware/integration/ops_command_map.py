from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IntegrationOpsCommand:
    command_id: str
    method: str
    path_template: str
    description: str


OPS_INTEGRATION_COMMANDS: tuple[IntegrationOpsCommand, ...] = (
    IntegrationOpsCommand(
        command_id="auth_login",
        method="POST",
        path_template="/auth/login",
        description="Authenticate admin, web user, and device user",
    ),
    IntegrationOpsCommand(
        command_id="admin_blog_publish",
        method="POST",
        path_template="/admin/content/blog/posts",
        description="Admin publishes blog post",
    ),
    IntegrationOpsCommand(
        command_id="blog_list",
        method="GET",
        path_template="/blog/api/posts",
        description="User/device reads blog feed",
    ),
    IntegrationOpsCommand(
        command_id="blog_get",
        method="GET",
        path_template="/blog/api/posts/{post_id}",
        description="User/device reads one blog post",
    ),
    IntegrationOpsCommand(
        command_id="support_ticket_create",
        method="POST",
        path_template="/support/api/tickets",
        description="User creates support ticket",
    ),
    IntegrationOpsCommand(
        command_id="support_messages_list",
        method="GET",
        path_template="/support/api/tickets/{ticket_id}/messages",
        description="User reads support message thread",
    ),
    IntegrationOpsCommand(
        command_id="support_tickets_list",
        method="GET",
        path_template="/support/api/tickets",
        description="User reads support tickets",
    ),
    IntegrationOpsCommand(
        command_id="admin_support_tickets_list",
        method="GET",
        path_template="/admin/content/support/tickets",
        description="Admin reviews support queue",
    ),
    IntegrationOpsCommand(
        command_id="admin_support_reply",
        method="POST",
        path_template="/admin/content/support/tickets/{ticket_id}/reply",
        description="Admin replies in support ticket",
    ),
    IntegrationOpsCommand(
        command_id="admin_support_status",
        method="POST",
        path_template="/admin/content/support/tickets/{ticket_id}/status",
        description="Admin updates support ticket status",
    ),
)


def command_path_set() -> set[str]:
    return {item.path_template for item in OPS_INTEGRATION_COMMANDS}
