from __future__ import annotations

from .models import ConnectionState, InfoScreenData, ShellState
from .screens import build_info_screen
from .server_api import GatewayError, TelemetryGateway


class M5TabShell:
    def __init__(self, gateway: TelemetryGateway) -> None:
        self._gateway = gateway
        self._state = ShellState(
            connection_state=ConnectionState.DISCONNECTED,
            connected=False,
            last_sync_ms=None,
            last_error=None,
        )

    @property
    def state(self) -> ShellState:
        return self._state

    def connect(self, *, now_ms: int) -> ShellState:
        self._state = ShellState(
            connection_state=ConnectionState.CONNECTING,
            connected=False,
            last_sync_ms=self._state.last_sync_ms,
            last_error=None,
        )

        try:
            payload = self._gateway.health()
        except GatewayError as exc:
            self._state = ShellState(
                connection_state=ConnectionState.DISCONNECTED,
                connected=False,
                last_sync_ms=self._state.last_sync_ms,
                last_error=f"{exc.code}:{exc.message}",
            )
            return self._state

        health_ok = payload.get("status") == "ok"
        self._state = ShellState(
            connection_state=ConnectionState.CONNECTED if health_ok else ConnectionState.DEGRADED,
            connected=health_ok,
            last_sync_ms=now_ms,
            last_error=None if health_ok else "health_not_ok",
        )
        return self._state

    def load_info_screen(self, *, now_ms: int, session_token: str | None = None) -> InfoScreenData:
        bundle = self._gateway.telemetry_bundle(session_token=session_token)
        screen = build_info_screen(telemetry_bundle=bundle, generated_at_ms=now_ms)

        if screen.health_status == "ok":
            self._state = ShellState(
                connection_state=ConnectionState.CONNECTED,
                connected=True,
                last_sync_ms=now_ms,
                last_error=None,
            )
        else:
            self._state = ShellState(
                connection_state=ConnectionState.DEGRADED,
                connected=False,
                last_sync_ms=now_ms,
                last_error="health_not_ok",
            )

        return screen
