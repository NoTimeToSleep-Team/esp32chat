from __future__ import annotations

from typing import Any

from ..server_api import CommandSender


class ConsoleChatGateway:
    def __init__(self, sender: CommandSender) -> None:
        self._sender = sender

    def list_chats(self, *, session_token: str) -> dict[str, Any]:
        return self._sender.send(
            method="GET",
            path="/chat/api/chats",
            query={"session_token": session_token},
        )

    def list_messages(
        self,
        *,
        session_token: str,
        chat_id: int,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        return self._sender.send(
            method="GET",
            path=f"/chat/api/chats/{chat_id}/messages",
            query={
                "session_token": session_token,
                "limit": str(limit),
                "offset": str(offset),
            },
        )

    def send_message(
        self,
        *,
        session_token: str,
        chat_id: int,
        body_text: str,
        client_message_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "session_token": session_token,
            "body_text": body_text,
        }
        if client_message_id is not None:
            payload["client_message_id"] = client_message_id

        return self._sender.send(
            method="POST",
            path=f"/chat/api/chats/{chat_id}/messages",
            json_payload=payload,
        )
