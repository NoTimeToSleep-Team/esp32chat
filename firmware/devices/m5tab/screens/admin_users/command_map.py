from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AdminUsersCommand:
    command_id: str
    method: str
    path_template: str
    description: str


M5TAB_ADMIN_USERS_COMMANDS: tuple[AdminUsersCommand, ...] = (
    AdminUsersCommand(
        command_id="admin_users_list",
        method="GET",
        path_template="/admin/users",
        description="Read users list for admin screen",
    ),
    AdminUsersCommand(
        command_id="admin_user_get",
        method="GET",
        path_template="/admin/users/{user_id}",
        description="Read single user details",
    ),
    AdminUsersCommand(
        command_id="admin_user_ban",
        method="POST",
        path_template="/admin/users/{user_id}/ban",
        description="Ban target user",
    ),
    AdminUsersCommand(
        command_id="admin_user_unban",
        method="POST",
        path_template="/admin/users/{user_id}/unban",
        description="Unban target user",
    ),
    AdminUsersCommand(
        command_id="admin_user_blacklist_device",
        method="POST",
        path_template="/admin/users/{user_id}/blacklist-device",
        description="Blacklist user device",
    ),
    AdminUsersCommand(
        command_id="admin_user_unblacklist_device",
        method="POST",
        path_template="/admin/users/{user_id}/unblacklist-device",
        description="Remove device from blacklist",
    ),
    AdminUsersCommand(
        command_id="admin_user_delete",
        method="DELETE",
        path_template="/admin/users/{user_id}",
        description="Delete user account",
    ),
)


def admin_users_command_path_set() -> set[str]:
    return {item.path_template for item in M5TAB_ADMIN_USERS_COMMANDS}
