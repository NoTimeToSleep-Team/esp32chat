from __future__ import annotations

from firmware.devices.m5cardputer_client.config import M5CardputerClientConfig
from firmware.devices.m5cardputer_client.ui.controller import M5CardputerHandheldClientController

from ..config import M5StickCPlus2Config
from ..server_api import CommandSender


class M5StickCPlus2ClientController:
    def __init__(self, *, config: M5StickCPlus2Config, sender: CommandSender) -> None:
        shared_config = M5CardputerClientConfig(
            profile_id=config.profile_id,
            base_url=config.base_url,
            request_timeout_s=config.request_timeout_s,
            client_kind=config.client_kind,
        )
        self._shared = M5CardputerHandheldClientController(config=shared_config, sender=sender)

    @property
    def session(self):
        return self._shared.session

    def secure_login(self, *, login: str, password: str):
        return self._shared.secure_login(login=login, password=password)

    def logout(self) -> bool:
        return self._shared.logout()

    def list_chats(self):
        return self._shared.list_chats()

    def load_messages(self, *, chat_id: int, limit: int = 100, offset: int = 0):
        return self._shared.load_messages(chat_id=chat_id, limit=limit, offset=offset)

    def send_text(self, *, chat_id: int, body_text: str, client_message_id: str | None = None):
        return self._shared.send_text(
            chat_id=chat_id,
            body_text=body_text,
            client_message_id=client_message_id,
        )

    def list_posts(self, *, limit: int = 20, offset: int = 0):
        return self._shared.list_posts(limit=limit, offset=offset)

    def get_post(self, *, post_id: int):
        return self._shared.get_post(post_id=post_id)
