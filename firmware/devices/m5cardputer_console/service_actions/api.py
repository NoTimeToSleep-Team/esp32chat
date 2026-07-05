from __future__ import annotations

from typing import Any

from ..server_api import CommandSender


class ConsoleServiceActionsGateway:
    def __init__(self, sender: CommandSender) -> None:
        self._sender = sender

    def health(self) -> dict[str, Any]:
        return self._sender.send(method="GET", path="/health")

    def readiness(self) -> dict[str, Any]:
        return self._sender.send(method="GET", path="/health/ready")

    def mode(self) -> dict[str, Any]:
        return self._sender.send(method="GET", path="/mode")

    def limits(self, *, session_token: str) -> dict[str, Any]:
        return self._sender.send(
            method="GET",
            path="/account/api/limits",
            query={"session_token": session_token},
        )
