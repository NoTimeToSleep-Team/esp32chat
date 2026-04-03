from __future__ import annotations

from typing import Any, Mapping

from .config import M5StickCPlus2Config
from .models import CompactScreen, CompactSession, CompactShellState, ConnectionState, disconnected_state
from .server_api import CompactAuthGateway


class M5StickCPlus2Shell:
    def __init__(self, gateway: CompactAuthGateway, config: M5StickCPlus2Config) -> None:
        self._gateway = gateway
        self._config = config
        self._state = disconnected_state()

    @property
    def state(self) -> CompactShellState:
        return self._state

    def connect(self, *, now_ms: int) -> CompactShellState:
        if self._state.connection_state == ConnectionState.AUTHENTICATED:
            return self._state

        self._state = CompactShellState(
            connection_state=ConnectionState.CONNECTING,
            connected=False,
            session=None,
            active_screen=self._state.active_screen,
            last_sync_ms=now_ms,
            last_error_code=None,
        )

        self._state = CompactShellState(
            connection_state=ConnectionState.CONNECTED,
            connected=True,
            session=None,
            active_screen=CompactScreen.HOME,
            last_sync_ms=now_ms,
            last_error_code=None,
        )
        return self._state

    def secure_login(self, *, login: str, password: str, now_ms: int) -> CompactShellState:
        if self._state.connection_state == ConnectionState.DISCONNECTED:
            self.connect(now_ms=now_ms)

        payload = self._gateway.login(
            login=login,
            password=password,
            client_kind=self._config.client_kind,
        )
        session = _parse_session_payload(payload)

        self._state = CompactShellState(
            connection_state=ConnectionState.AUTHENTICATED,
            connected=True,
            session=session,
            active_screen=CompactScreen.HOME,
            last_sync_ms=now_ms,
            last_error_code=None,
        )
        return self._state

    def resume_session(self, *, session_token: str, now_ms: int) -> CompactShellState:
        payload = self._gateway.get_session(
            session_token=session_token,
            client_kind=self._config.client_kind,
        )
        session = _parse_session_payload(payload)

        self._state = CompactShellState(
            connection_state=ConnectionState.AUTHENTICATED,
            connected=True,
            session=session,
            active_screen=self._state.active_screen,
            last_sync_ms=now_ms,
            last_error_code=None,
        )
        return self._state

    def open_screen(self, *, screen: CompactScreen, now_ms: int) -> CompactShellState:
        if self._state.session is None:
            raise RuntimeError("open_screen requires authenticated session")

        self._state = CompactShellState(
            connection_state=ConnectionState.AUTHENTICATED,
            connected=True,
            session=self._state.session,
            active_screen=screen,
            last_sync_ms=now_ms,
            last_error_code=None,
        )
        return self._state

    def logout(self, *, now_ms: int) -> CompactShellState:
        token = self._state.session.token if self._state.session is not None else None
        if token:
            payload = self._gateway.logout(session_token=token)
            if payload.get("status") != "ok":
                raise RuntimeError("logout returned unexpected status")

        self._state = CompactShellState(
            connection_state=ConnectionState.CONNECTED,
            connected=True,
            session=None,
            active_screen=CompactScreen.HOME,
            last_sync_ms=now_ms,
            last_error_code=None,
        )
        return self._state


def _parse_session_payload(payload: Mapping[str, Any]) -> CompactSession:
    if payload.get("status") != "ok":
        raise RuntimeError(f"unexpected payload status: {payload.get('status')}")

    user_raw = payload.get("user")
    if not isinstance(user_raw, Mapping):
        raise RuntimeError("auth payload.user must be object")

    session_raw = payload.get("session")
    if not isinstance(session_raw, Mapping):
        raise RuntimeError("auth payload.session must be object")

    return CompactSession(
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
