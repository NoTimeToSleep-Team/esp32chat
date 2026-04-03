from __future__ import annotations

from .config import M5StickCPlus2Config
from .models import CompactScreen, CompactShellState
from .server_api import CompactAuthGateway
from .shell import M5StickCPlus2Shell


class M5StickCPlus2Controller:
    def __init__(
        self,
        *,
        config: M5StickCPlus2Config,
        gateway: CompactAuthGateway,
        shell: M5StickCPlus2Shell | None = None,
    ) -> None:
        self._config = config
        self._gateway = gateway
        self._shell = shell or M5StickCPlus2Shell(gateway=gateway, config=config)

    @property
    def config(self) -> M5StickCPlus2Config:
        return self._config

    @property
    def shell_state(self) -> CompactShellState:
        return self._shell.state

    def start_shell(self, *, now_ms: int) -> CompactShellState:
        return self._shell.connect(now_ms=now_ms)

    def secure_login(self, *, login: str, password: str, now_ms: int) -> CompactShellState:
        return self._shell.secure_login(login=login, password=password, now_ms=now_ms)

    def resume_session(self, *, session_token: str, now_ms: int) -> CompactShellState:
        return self._shell.resume_session(session_token=session_token, now_ms=now_ms)

    def open_screen(self, *, screen: CompactScreen, now_ms: int) -> CompactShellState:
        return self._shell.open_screen(screen=screen, now_ms=now_ms)

    def logout(self, *, now_ms: int) -> CompactShellState:
        return self._shell.logout(now_ms=now_ms)
