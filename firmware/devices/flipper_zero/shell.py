from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .config import FlipperZeroConfig
from .models import CapabilitySnapshot, ConnectionState, FlipperScreen, FlipperSession, FlipperShellState, disconnected_state
from .server_api import FlipperAuthGateway


class CapabilityDetector(Protocol):
    def detect(self, *, now_ms: int) -> CapabilitySnapshot:
        ...


@dataclass(frozen=True)
class StaticCapabilityDetector:
    wifi_dev_board_attached: bool = False

    def detect(self, *, now_ms: int) -> CapabilitySnapshot:
        network_mode = self.wifi_dev_board_attached
        return CapabilitySnapshot(
            wifi_dev_board_attached=self.wifi_dev_board_attached,
            network_mode_enabled=network_mode,
            mode="network" if network_mode else "limited_local",
            reason="wifi_dev_board_detected" if network_mode else "wifi_dev_board_missing",
            detected_at_ms=now_ms,
        )


class FlipperZeroShell:
    def __init__(
        self,
        gateway: FlipperAuthGateway,
        config: FlipperZeroConfig,
        capability_detector: CapabilityDetector,
    ) -> None:
        self._gateway = gateway
        self._config = config
        self._capability_detector = capability_detector
        self._state = disconnected_state()

    @property
    def state(self) -> FlipperShellState:
        return self._state

    def detect_capabilities(self, *, now_ms: int) -> FlipperShellState:
        snapshot = self._capability_detector.detect(now_ms=now_ms)

        if not snapshot.network_mode_enabled:
            self._state = FlipperShellState(
                connection_state=ConnectionState.LIMITED,
                connected=False,
                capability=snapshot,
                session=None,
                active_screen=FlipperScreen.HOME,
                last_sync_ms=now_ms,
                last_error_code="network_module_missing",
            )
            return self._state

        if self._state.session is not None:
            self._state = FlipperShellState(
                connection_state=ConnectionState.AUTHENTICATED,
                connected=True,
                capability=snapshot,
                session=self._state.session,
                active_screen=self._state.active_screen,
                last_sync_ms=now_ms,
                last_error_code=None,
            )
            return self._state

        self._state = FlipperShellState(
            connection_state=ConnectionState.DISCONNECTED,
            connected=False,
            capability=snapshot,
            session=None,
            active_screen=FlipperScreen.HOME,
            last_sync_ms=now_ms,
            last_error_code=None,
        )
        return self._state

    def connect(self, *, now_ms: int) -> FlipperShellState:
        if self._state.connection_state == ConnectionState.AUTHENTICATED:
            return self._state

        capability = self._state.capability or self._capability_detector.detect(now_ms=now_ms)
        if not capability.network_mode_enabled:
            self._state = FlipperShellState(
                connection_state=ConnectionState.LIMITED,
                connected=False,
                capability=capability,
                session=None,
                active_screen=FlipperScreen.HOME,
                last_sync_ms=now_ms,
                last_error_code="network_module_missing",
            )
            return self._state

        self._state = FlipperShellState(
            connection_state=ConnectionState.CONNECTING,
            connected=False,
            capability=capability,
            session=None,
            active_screen=self._state.active_screen,
            last_sync_ms=now_ms,
            last_error_code=None,
        )

        health_payload = self._gateway.health()
        if health_payload.get("status") != "ok":
            raise RuntimeError("health probe failed for network mode")

        self._state = FlipperShellState(
            connection_state=ConnectionState.CONNECTED,
            connected=True,
            capability=capability,
            session=None,
            active_screen=FlipperScreen.HOME,
            last_sync_ms=now_ms,
            last_error_code=None,
        )
        return self._state

    def secure_login(self, *, login: str, password: str, now_ms: int) -> FlipperShellState:
        if self._state.connection_state in (ConnectionState.DISCONNECTED, ConnectionState.LIMITED):
            self.connect(now_ms=now_ms)

        if self._state.connection_state == ConnectionState.LIMITED:
            raise RuntimeError("secure_login unavailable in limited mode without wifi dev board")

        payload = self._gateway.login(
            login=login,
            password=password,
            client_kind=self._config.client_kind,
        )
        session = _parse_session_payload(payload)
        capability = self._state.capability or self._capability_detector.detect(now_ms=now_ms)

        self._state = FlipperShellState(
            connection_state=ConnectionState.AUTHENTICATED,
            connected=True,
            capability=capability,
            session=session,
            active_screen=FlipperScreen.HOME,
            last_sync_ms=now_ms,
            last_error_code=None,
        )
        return self._state

    def resume_session(self, *, session_token: str, now_ms: int) -> FlipperShellState:
        capability = self._state.capability or self._capability_detector.detect(now_ms=now_ms)
        if not capability.network_mode_enabled:
            raise RuntimeError("resume_session unavailable in limited mode without wifi dev board")

        payload = self._gateway.get_session(
            session_token=session_token,
            client_kind=self._config.client_kind,
        )
        session = _parse_session_payload(payload)

        self._state = FlipperShellState(
            connection_state=ConnectionState.AUTHENTICATED,
            connected=True,
            capability=capability,
            session=session,
            active_screen=self._state.active_screen,
            last_sync_ms=now_ms,
            last_error_code=None,
        )
        return self._state

    def open_screen(self, *, screen: FlipperScreen, now_ms: int) -> FlipperShellState:
        if self._state.session is None:
            raise RuntimeError("open_screen requires authenticated session")

        self._state = FlipperShellState(
            connection_state=ConnectionState.AUTHENTICATED,
            connected=True,
            capability=self._state.capability,
            session=self._state.session,
            active_screen=screen,
            last_sync_ms=now_ms,
            last_error_code=None,
        )
        return self._state

    def logout(self, *, now_ms: int) -> FlipperShellState:
        token = self._state.session.token if self._state.session is not None else None
        if token:
            payload = self._gateway.logout(session_token=token)
            if payload.get("status") != "ok":
                raise RuntimeError("logout returned unexpected status")

        capability = self._state.capability or self._capability_detector.detect(now_ms=now_ms)
        if capability.network_mode_enabled:
            self._state = FlipperShellState(
                connection_state=ConnectionState.CONNECTED,
                connected=True,
                capability=capability,
                session=None,
                active_screen=FlipperScreen.HOME,
                last_sync_ms=now_ms,
                last_error_code=None,
            )
            return self._state

        self._state = FlipperShellState(
            connection_state=ConnectionState.LIMITED,
            connected=False,
            capability=capability,
            session=None,
            active_screen=FlipperScreen.HOME,
            last_sync_ms=now_ms,
            last_error_code="network_module_missing",
        )
        return self._state


def _parse_session_payload(payload: Mapping[str, Any]) -> FlipperSession:
    if payload.get("status") != "ok":
        raise RuntimeError(f"unexpected payload status: {payload.get('status')}")

    user_raw = payload.get("user")
    if not isinstance(user_raw, Mapping):
        raise RuntimeError("auth payload.user must be object")

    session_raw = payload.get("session")
    if not isinstance(session_raw, Mapping):
        raise RuntimeError("auth payload.session must be object")

    return FlipperSession(
        user_id=_to_int(user_raw.get("id"), default=0),
        login=_to_str(user_raw.get("login"), default=""),
        role=_to_str(user_raw.get("role"), default="unknown"),
        user_status=_to_str(user_raw.get("status"), default="unknown"),
        access_mode=_to_str(payload.get("access_mode"), default="unknown"),
        token=_to_str(session_raw.get("token"), default=""),
        created_at_ms=_to_int(session_raw.get("created_at_ms"), default=0),
        expires_at_ms=_to_int(session_raw.get("expires_at_ms"), default=0),
    )


def _to_str(value: Any, *, default: str) -> str:
    if isinstance(value, str):
        return value
    return default


def _to_int(value: Any, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return default
