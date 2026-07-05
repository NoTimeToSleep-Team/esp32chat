from __future__ import annotations

from typing import Any

from .api import AdminUsersGateway
from .models import AdminUserView, DeviceBlacklistView, UserDeleteResult, UsersScreenData
from .presenter import build_users_screen, parse_blacklist_entry, parse_delete_result, parse_user


class M5TabAdminUsersController:
    def __init__(self, gateway: AdminUsersGateway) -> None:
        self._gateway = gateway

    def list_users(
        self,
        *,
        session_token: str,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> UsersScreenData:
        payload = self._gateway.list_users(
            session_token=session_token,
            status=status,
            limit=limit,
            offset=offset,
        )
        return build_users_screen(payload, status_filter=status)

    def get_user(self, *, session_token: str, user_id: int) -> AdminUserView:
        payload = self._gateway.get_user(session_token=session_token, user_id=user_id)
        if payload.get("status") != "ok":
            raise RuntimeError("unexpected get_user status")
        user_payload = payload.get("user")
        if not isinstance(user_payload, dict):
            raise RuntimeError("get_user payload.user must be object")
        return parse_user(user_payload)

    def ban_user(self, *, session_token: str, user_id: int, reason: str | None = None) -> AdminUserView:
        payload = self._gateway.ban_user(session_token=session_token, user_id=user_id, reason=reason)
        return self._extract_user(payload, operation="ban_user")

    def unban_user(self, *, session_token: str, user_id: int) -> AdminUserView:
        payload = self._gateway.unban_user(session_token=session_token, user_id=user_id)
        return self._extract_user(payload, operation="unban_user")

    def blacklist_device(
        self,
        *,
        session_token: str,
        user_id: int,
        reason: str | None = None,
        device_id: str | None = None,
    ) -> tuple[AdminUserView, DeviceBlacklistView]:
        payload = self._gateway.blacklist_device(
            session_token=session_token,
            user_id=user_id,
            reason=reason,
            device_id=device_id,
        )
        user = self._extract_user(payload, operation="blacklist_device")
        entry_payload = payload.get("blacklist_entry")
        if not isinstance(entry_payload, dict):
            raise RuntimeError("blacklist_device payload.blacklist_entry must be object")
        entry = parse_blacklist_entry(entry_payload)
        return user, entry

    def unblacklist_device(
        self,
        *,
        session_token: str,
        user_id: int,
        device_id: str | None = None,
    ) -> AdminUserView:
        payload = self._gateway.unblacklist_device(
            session_token=session_token,
            user_id=user_id,
            device_id=device_id,
        )
        return self._extract_user(payload, operation="unblacklist_device")

    def delete_user(self, *, session_token: str, user_id: int) -> UserDeleteResult:
        payload = self._gateway.delete_user(session_token=session_token, user_id=user_id)
        return parse_delete_result(payload)

    def register_admin_action_incident(
        self,
        *,
        session_token: str,
        title: str,
        details: dict[str, Any],
    ) -> dict[str, Any]:
        payload = self._gateway.create_incident(
            session_token=session_token,
            title=title,
            details=details,
        )
        if payload.get("status") != "ok":
            raise RuntimeError("register_admin_action_incident failed")
        return payload

    @staticmethod
    def _extract_user(payload: dict[str, Any], *, operation: str) -> AdminUserView:
        if payload.get("status") != "ok":
            raise RuntimeError(f"{operation} returned unexpected status")
        user_payload = payload.get("user")
        if not isinstance(user_payload, dict):
            raise RuntimeError(f"{operation} payload.user must be object")
        return parse_user(user_payload)
