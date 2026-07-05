from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AdminOpsCommand:
    command_id: str
    method: str
    path_template: str
    description: str


M5TAB_ADMIN_OPS_COMMANDS: tuple[AdminOpsCommand, ...] = (
    AdminOpsCommand(
        command_id="admin_support_tickets_list",
        method="GET",
        path_template="/admin/content/support/tickets",
        description="Read support tickets queue",
    ),
    AdminOpsCommand(
        command_id="admin_support_ticket_reply",
        method="POST",
        path_template="/admin/content/support/tickets/{ticket_id}/reply",
        description="Reply to support ticket",
    ),
    AdminOpsCommand(
        command_id="admin_support_ticket_status",
        method="POST",
        path_template="/admin/content/support/tickets/{ticket_id}/status",
        description="Change support ticket status",
    ),
    AdminOpsCommand(
        command_id="admin_blog_posts_list",
        method="GET",
        path_template="/admin/content/blog/posts",
        description="Read blog posts for admin panel",
    ),
    AdminOpsCommand(
        command_id="admin_blog_post_publish",
        method="POST",
        path_template="/admin/content/blog/posts",
        description="Publish blog post",
    ),
    AdminOpsCommand(
        command_id="rfid_cards_list",
        method="GET",
        path_template="/rfid/api/cards",
        description="Read RFID cards list",
    ),
    AdminOpsCommand(
        command_id="rfid_card_enroll",
        method="POST",
        path_template="/rfid/api/cards",
        description="Enroll RFID card",
    ),
    AdminOpsCommand(
        command_id="rfid_card_toggle_active",
        method="POST",
        path_template="/rfid/api/cards/{card_id}/active",
        description="Toggle RFID card active state",
    ),
    AdminOpsCommand(
        command_id="admin_mode_state",
        method="GET",
        path_template="/admin/mode/state",
        description="Read admin mode state and safe sequence",
    ),
    AdminOpsCommand(
        command_id="admin_mode_set",
        method="POST",
        path_template="/admin/mode/set",
        description="Set access mode with hold requirement",
    ),
)


def admin_ops_command_path_set() -> set[str]:
    return {item.path_template for item in M5TAB_ADMIN_OPS_COMMANDS}
