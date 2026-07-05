from __future__ import annotations

from typing import Any, Mapping

from firmware.devices.m5cardputer_console.blog import ConsoleBlogGateway, M5CardputerConsoleBlogController
from firmware.devices.m5cardputer_console.chat import ConsoleChatGateway, M5CardputerConsoleChatController
from firmware.devices.m5cardputer_console.server_api import CommandSender, ConsoleAuthGateway

from ..config import M5CardputerClientConfig
from .models import HandheldSession


class M5CardputerHandheldClientController:
    def __init__(self, *, config: M5CardputerClientConfig, sender: CommandSender) -> None:
        self._config = config
        self._auth = ConsoleAuthGateway(sender)
        self._chat = M5CardputerConsoleChatController(ConsoleChatGateway(sender))
        self._blog = M5CardputerConsoleBlogController(ConsoleBlogGateway(sender))
        self._session: HandheldSession | None = None

    @property
    def session(self) -> HandheldSession | None:
        return self._session

    def secure_login(self, *, login: str, password: str) -> HandheldSession:
        payload = self._auth.login(
            login=login,
            password=password,
            client_kind=self._config.client_kind,
        )
        self._session = _parse_session(payload)
        return self._session

    def logout(self) -> bool:
        if self._session is None:
            return False
        payload = self._auth.logout(session_token=self._session.session_token)
        if payload.get("status") != "ok":
            raise RuntimeError("logout returned unexpected status")
        revoked = bool(payload.get("revoked"))
        self._session = None
        return revoked

    def list_chats(self):
        session = self._require_session()
        return self._chat.list_chats(session_token=session.session_token)

    def load_messages(self, *, chat_id: int, limit: int = 100, offset: int = 0):
        session = self._require_session()
        return self._chat.load_messages(
            session_token=session.session_token,
            chat_id=chat_id,
            limit=limit,
            offset=offset,
        )

    def send_text(self, *, chat_id: int, body_text: str, client_message_id: str | None = None):
        session = self._require_session()
        return self._chat.send_text(
            session_token=session.session_token,
            chat_id=chat_id,
            body_text=body_text,
            client_message_id=client_message_id,
        )

    def list_posts(self, *, limit: int = 20, offset: int = 0):
        session = self._require_session()
        return self._blog.list_posts(
            session_token=session.session_token,
            limit=limit,
            offset=offset,
        )

    def get_post(self, *, post_id: int):
        session = self._require_session()
        return self._blog.get_post(session_token=session.session_token, post_id=post_id)

    def _require_session(self) -> HandheldSession:
        if self._session is None:
            raise RuntimeError("operation requires authenticated handheld session")
        return self._session


def _parse_session(payload: Mapping[str, Any]) -> HandheldSession:
    if payload.get("status") != "ok":
        raise RuntimeError(f"unexpected payload status: {payload.get('status')}")

    user_raw = payload.get("user")
    if not isinstance(user_raw, Mapping):
        raise RuntimeError("auth payload.user must be object")
    session_raw = payload.get("session")
    if not isinstance(session_raw, Mapping):
        raise RuntimeError("auth payload.session must be object")

    return HandheldSession(
        user_id=_to_int(user_raw.get("id"), default=0),
        login=_to_str(user_raw.get("login"), default=""),
        role=_to_str(user_raw.get("role"), default="unknown"),
        status=_to_str(user_raw.get("status"), default="unknown"),
        access_mode=_to_str(payload.get("access_mode"), default="unknown"),
        session_token=_to_str(session_raw.get("token"), default=""),
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
