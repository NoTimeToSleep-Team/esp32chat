from __future__ import annotations

from typing import Any, Mapping

from ...server_api import CommandSender


class AdminUsersGateway:
    def __init__(self, sender: CommandSender) -> None:
        self._sender = sender

    def list_users(
        self,
        *,
        session_token: str,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        query = {
            "session_token": session_token,
            "limit": str(limit),
            "offset": str(offset),
        }
        if status:
            query["status"] = status

        return self._sender.send(
            method="GET",
            path="/admin/users",
            query=query,
        )

    def get_user(self, *, session_token: str, user_id: int) -> dict[str, Any]:
        return self._sender.send(
            method="GET",
            path=f"/admin/users/{user_id}",
            query={"session_token": session_token},
        )

    def ban_user(self, *, session_token: str, user_id: int, reason: str | None = None) -> dict[str, Any]:
        return self._sender.send(
            method="POST",
            path=f"/admin/users/{user_id}/ban",
            json_payload={"session_token": session_token, "reason": reason},
        )

    def unban_user(self, *, session_token: str, user_id: int) -> dict[str, Any]:
        return self._sender.send(
            method="POST",
            path=f"/admin/users/{user_id}/unban",
            json_payload={"session_token": session_token},
        )

    def blacklist_device(
        self,
        *,
        session_token: str,
        user_id: int,
        reason: str | None = None,
        device_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "session_token": session_token,
            "reason": reason,
        }
        if device_id is not None:
            payload["device_id"] = device_id

        return self._sender.send(
            method="POST",
            path=f"/admin/users/{user_id}/blacklist-device",
            json_payload=payload,
        )

    def unblacklist_device(
        self,
        *,
        session_token: str,
        user_id: int,
        device_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"session_token": session_token}
        if device_id is not None:
            payload["device_id"] = device_id

        return self._sender.send(
            method="POST",
            path=f"/admin/users/{user_id}/unblacklist-device",
            json_payload=payload,
        )

    def delete_user(self, *, session_token: str, user_id: int) -> dict[str, Any]:
        return self._sender.send(
            method="DELETE",
            path=f"/admin/users/{user_id}",
            query={"session_token": session_token},
        )

    def create_incident(
        self,
        *,
        session_token: str,
        title: str,
        details: Mapping[str, Any],
    ) -> dict[str, Any]:
        return self._sender.send(
            method="POST",
            path="/ops/api/incidents",
            json_payload={
                "session_token": session_token,
                "level": "warning",
                "title": title,
                "source": "m5tab_admin_users",
                "details": dict(details),
            },
        )
