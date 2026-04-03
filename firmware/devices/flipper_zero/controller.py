from __future__ import annotations

from .config import FlipperZeroConfig
from .models import FlipperScreen, FlipperShellState
from .server_api import FlipperAuthGateway
from .shell import CapabilityDetector, FlipperZeroShell, StaticCapabilityDetector


class FlipperZeroController:
    def __init__(
        self,
        *,
        config: FlipperZeroConfig,
        gateway: FlipperAuthGateway,
        capability_detector: CapabilityDetector | None = None,
        shell: FlipperZeroShell | None = None,
    ) -> None:
        self._config = config
        self._gateway = gateway
        detector = capability_detector or StaticCapabilityDetector(wifi_dev_board_attached=False)
        self._shell = shell or FlipperZeroShell(
            gateway=gateway,
            config=config,
            capability_detector=detector,
        )

    @property
    def config(self) -> FlipperZeroConfig:
        return self._config

    @property
    def shell_state(self) -> FlipperShellState:
        return self._shell.state

    def detect_capabilities(self, *, now_ms: int) -> FlipperShellState:
        return self._shell.detect_capabilities(now_ms=now_ms)

    def start_shell(self, *, now_ms: int) -> FlipperShellState:
        return self._shell.connect(now_ms=now_ms)

    def secure_login(self, *, login: str, password: str, now_ms: int) -> FlipperShellState:
        return self._shell.secure_login(login=login, password=password, now_ms=now_ms)

    def resume_session(self, *, session_token: str, now_ms: int) -> FlipperShellState:
        return self._shell.resume_session(session_token=session_token, now_ms=now_ms)

    def open_screen(self, *, screen: FlipperScreen, now_ms: int) -> FlipperShellState:
        return self._shell.open_screen(screen=screen, now_ms=now_ms)

    def logout(self, *, now_ms: int) -> FlipperShellState:
        return self._shell.logout(now_ms=now_ms)
