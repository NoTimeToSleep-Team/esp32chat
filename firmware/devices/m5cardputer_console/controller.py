from __future__ import annotations

from .blog import ConsoleBlogGateway, M5CardputerConsoleBlogController
from .chat import ConsoleChatGateway, M5CardputerConsoleChatController
from .config import M5CardputerConsoleConfig
from .models import ConsoleShellState, NavigationScreen
from .server_api import ConsoleAuthGateway
from .service_actions import ConsoleServiceActionsGateway, M5CardputerConsoleServiceController
from .shell import M5CardputerConsoleShell


class M5CardputerConsoleController:
    def __init__(
        self,
        *,
        config: M5CardputerConsoleConfig,
        gateway: ConsoleAuthGateway,
        blog_controller: M5CardputerConsoleBlogController | None = None,
        chat_controller: M5CardputerConsoleChatController | None = None,
        service_controller: M5CardputerConsoleServiceController | None = None,
        shell: M5CardputerConsoleShell | None = None,
    ) -> None:
        self._config = config
        self._gateway = gateway
        self._blog = blog_controller or M5CardputerConsoleBlogController(ConsoleBlogGateway(gateway.sender))
        self._chat = chat_controller or M5CardputerConsoleChatController(ConsoleChatGateway(gateway.sender))
        self._service_actions = service_controller or M5CardputerConsoleServiceController(
            ConsoleServiceActionsGateway(gateway.sender)
        )
        self._shell = shell or M5CardputerConsoleShell(gateway=gateway, config=config)

    @property
    def config(self) -> M5CardputerConsoleConfig:
        return self._config

    @property
    def shell_state(self) -> ConsoleShellState:
        return self._shell.state

    @property
    def chat(self) -> M5CardputerConsoleChatController:
        return self._chat

    @property
    def blog(self) -> M5CardputerConsoleBlogController:
        return self._blog

    @property
    def service_actions(self) -> M5CardputerConsoleServiceController:
        return self._service_actions

    def start_shell(self, *, now_ms: int) -> ConsoleShellState:
        return self._shell.connect(now_ms=now_ms)

    def secure_login(self, *, login: str, password: str, now_ms: int) -> ConsoleShellState:
        return self._shell.secure_login(login=login, password=password, now_ms=now_ms)

    def resume_session(self, *, session_token: str, now_ms: int) -> ConsoleShellState:
        return self._shell.resume_session(session_token=session_token, now_ms=now_ms)

    def open_screen(self, *, screen: NavigationScreen, now_ms: int) -> ConsoleShellState:
        return self._shell.open_screen(screen=screen, now_ms=now_ms)

    def logout(self, *, now_ms: int) -> ConsoleShellState:
        return self._shell.logout(now_ms=now_ms)
