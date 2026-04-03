from __future__ import annotations

from .api import ConsoleServiceActionsGateway
from .models import ConsoleServiceSnapshot
from .presenter import build_service_snapshot


class M5CardputerConsoleServiceController:
    def __init__(self, gateway: ConsoleServiceActionsGateway) -> None:
        self._gateway = gateway

    def refresh_shortcuts(self, *, session_token: str) -> ConsoleServiceSnapshot:
        health = self._gateway.health()
        readiness = self._gateway.readiness()
        mode = self._gateway.mode()
        limits = self._gateway.limits(session_token=session_token)

        return build_service_snapshot(
            health_payload=health,
            readiness_payload=readiness,
            mode_payload=mode,
            limits_payload=limits,
        )
