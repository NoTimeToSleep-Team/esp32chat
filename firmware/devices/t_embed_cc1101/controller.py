from __future__ import annotations

from .config import TEmbedCC1101Config
from .models import TEmbedScreen, TEmbedShellState
from .server_api import TEmbedAuthGateway
from .shell import TEmbedCC1101Shell


class TEmbedCC1101Controller:
    def __init__(
        self,
        *,
        config: TEmbedCC1101Config,
        gateway: TEmbedAuthGateway,
        shell: TEmbedCC1101Shell | None = None,
    ) -> None:
        self._config = config
        self._gateway = gateway
        self._shell = shell or TEmbedCC1101Shell(gateway=gateway, config=config)

    @property
    def config(self) -> TEmbedCC1101Config:
        return self._config

    @property
    def shell_state(self) -> TEmbedShellState:
        return self._shell.state

    def start_shell(self, *, now_ms: int) -> TEmbedShellState:
        return self._shell.connect(now_ms=now_ms)

    def secure_login(self, *, login: str, password: str, now_ms: int) -> TEmbedShellState:
        return self._shell.secure_login(login=login, password=password, now_ms=now_ms)

    def resume_session(self, *, session_token: str, now_ms: int) -> TEmbedShellState:
        return self._shell.resume_session(session_token=session_token, now_ms=now_ms)

    def open_screen(self, *, screen: TEmbedScreen, now_ms: int) -> TEmbedShellState:
        return self._shell.open_screen(screen=screen, now_ms=now_ms)

    def logout(self, *, now_ms: int) -> TEmbedShellState:
        return self._shell.logout(now_ms=now_ms)
