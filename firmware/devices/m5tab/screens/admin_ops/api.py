from __future__ import annotations

from typing import Any

from ...server_api import CommandSender


class AdminOpsGateway:
    def __init__(self, sender: CommandSender) -> None:
        self._sender = sender

    def list_support_tickets(
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
        if status is not None:
            query["status"] = status
        return self._sender.send(method="GET", path="/admin/content/support/tickets", query=query)

    def reply_support_ticket(
        self,
        *,
        session_token: str,
        ticket_id: int,
        body_text: str,
    ) -> dict[str, Any]:
        return self._sender.send(
            method="POST",
            path=f"/admin/content/support/tickets/{ticket_id}/reply",
            json_payload={
                "session_token": session_token,
                "body_text": body_text,
            },
        )

    def set_support_ticket_status(
        self,
        *,
        session_token: str,
        ticket_id: int,
        status: str,
    ) -> dict[str, Any]:
        return self._sender.send(
            method="POST",
            path=f"/admin/content/support/tickets/{ticket_id}/status",
            json_payload={
                "session_token": session_token,
                "status": status,
            },
        )

    def list_blog_posts(
        self,
        *,
        session_token: str,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        return self._sender.send(
            method="GET",
            path="/admin/content/blog/posts",
            query={
                "session_token": session_token,
                "limit": str(limit),
                "offset": str(offset),
            },
        )

    def publish_blog_post(
        self,
        *,
        session_token: str,
        title: str,
        body_text: str,
    ) -> dict[str, Any]:
        return self._sender.send(
            method="POST",
            path="/admin/content/blog/posts",
            json_payload={
                "session_token": session_token,
                "title": title,
                "body_text": body_text,
            },
        )

    def list_rfid_cards(
        self,
        *,
        session_token: str,
        include_inactive: bool = True,
        limit: int = 200,
        offset: int = 0,
    ) -> dict[str, Any]:
        return self._sender.send(
            method="GET",
            path="/rfid/api/cards",
            query={
                "session_token": session_token,
                "include_inactive": "true" if include_inactive else "false",
                "limit": str(limit),
                "offset": str(offset),
            },
        )

    def enroll_rfid_card(
        self,
        *,
        session_token: str,
        card_uid: str,
        card_label: str,
        note: str | None = None,
        is_active: bool = True,
    ) -> dict[str, Any]:
        return self._sender.send(
            method="POST",
            path="/rfid/api/cards",
            json_payload={
                "session_token": session_token,
                "card_uid": card_uid,
                "card_label": card_label,
                "note": note,
                "is_active": is_active,
            },
        )

    def set_rfid_card_active(
        self,
        *,
        session_token: str,
        card_id: int,
        is_active: bool,
    ) -> dict[str, Any]:
        return self._sender.send(
            method="POST",
            path=f"/rfid/api/cards/{card_id}/active",
            json_payload={
                "session_token": session_token,
                "is_active": is_active,
            },
        )

    def get_mode_state(self, *, session_token: str) -> dict[str, Any]:
        return self._sender.send(
            method="GET",
            path="/admin/mode/state",
            query={"session_token": session_token},
        )

    def set_mode(
        self,
        *,
        session_token: str,
        access_mode: str,
        hold_seconds: int,
    ) -> dict[str, Any]:
        return self._sender.send(
            method="POST",
            path="/admin/mode/set",
            json_payload={
                "session_token": session_token,
                "access_mode": access_mode,
                "hold_seconds": hold_seconds,
            },
        )
