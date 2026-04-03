from __future__ import annotations

from firmware.devices.m5cardputer_console.blog import ConsoleBlogGateway, M5CardputerConsoleBlogController
from firmware.devices.m5cardputer_console.chat import ConsoleChatGateway, M5CardputerConsoleChatController

from ..config import FlipperZeroConfig
from ..controller import FlipperZeroController
from ..models import FlipperSession, FlipperShellState
from ..server_api import CommandSender, FlipperAuthGateway
from ..shell import CapabilityDetector, StaticCapabilityDetector


class FlipperZeroLimitedClientController:
    def __init__(
        self,
        *,
        config: FlipperZeroConfig,
        sender: CommandSender,
        capability_detector: CapabilityDetector | None = None,
    ) -> None:
        self._config = config
        self._sender = sender
        self._gateway = FlipperAuthGateway(sender)
        detector = capability_detector or StaticCapabilityDetector(wifi_dev_board_attached=False)
        self._shell = FlipperZeroController(
            config=config,
            gateway=self._gateway,
            capability_detector=detector,
        )
        self._chat = M5CardputerConsoleChatController(ConsoleChatGateway(sender))
        self._blog = M5CardputerConsoleBlogController(ConsoleBlogGateway(sender))

    @property
    def shell_state(self) -> FlipperShellState:
        return self._shell.shell_state

    @property
    def session(self) -> FlipperSession | None:
        return self._shell.shell_state.session

    def detect_capabilities(self, *, now_ms: int) -> FlipperShellState:
        return self._shell.detect_capabilities(now_ms=now_ms)

    def start_shell(self, *, now_ms: int) -> FlipperShellState:
        return self._shell.start_shell(now_ms=now_ms)

    def secure_login(self, *, login: str, password: str, now_ms: int) -> FlipperShellState:
        return self._shell.secure_login(login=login, password=password, now_ms=now_ms)

    def resume_session(self, *, session_token: str, now_ms: int) -> FlipperShellState:
        return self._shell.resume_session(session_token=session_token, now_ms=now_ms)

    def logout(self, *, now_ms: int) -> FlipperShellState:
        return self._shell.logout(now_ms=now_ms)

    def read_mode(self) -> dict[str, object]:
        return self._gateway.mode()

    def list_chats(self):
        session = self._require_session()
        return self._chat.list_chats(session_token=session.token)

    def load_messages(self, *, chat_id: int, limit: int = 100, offset: int = 0):
        session = self._require_session()
        return self._chat.load_messages(
            session_token=session.token,
            chat_id=chat_id,
            limit=limit,
            offset=offset,
        )

    def send_text(self, *, chat_id: int, body_text: str, client_message_id: str | None = None):
        session = self._require_session()
        return self._chat.send_text(
            session_token=session.token,
            chat_id=chat_id,
            body_text=body_text,
            client_message_id=client_message_id,
        )

    def list_posts(self, *, limit: int = 20, offset: int = 0):
        session = self._require_session()
        return self._blog.list_posts(
            session_token=session.token,
            limit=limit,
            offset=offset,
        )

    def get_post(self, *, post_id: int):
        session = self._require_session()
        return self._blog.get_post(session_token=session.token, post_id=post_id)

    def _require_session(self) -> FlipperSession:
        session = self.session
        if session is None:
            raise RuntimeError("operation requires authenticated flipper session")
        return session
