from __future__ import annotations

from typing import Any

from ..server_api import CommandSender


class ConsoleBlogGateway:
    def __init__(self, sender: CommandSender) -> None:
        self._sender = sender

    def list_posts(
        self,
        *,
        session_token: str,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        return self._sender.send(
            method="GET",
            path="/blog/api/posts",
            query={
                "session_token": session_token,
                "limit": str(limit),
                "offset": str(offset),
            },
        )

    def get_post(self, *, session_token: str, post_id: int) -> dict[str, Any]:
        return self._sender.send(
            method="GET",
            path=f"/blog/api/posts/{post_id}",
            query={"session_token": session_token},
        )
