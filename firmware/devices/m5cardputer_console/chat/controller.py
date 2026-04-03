from __future__ import annotations

from .api import ConsoleChatGateway
from .models import ChatHistoryScreenData, ChatListScreenData, ChatSendResult
from .presenter import build_chat_history, build_chat_list, parse_send_result


class M5CardputerConsoleChatController:
    def __init__(self, gateway: ConsoleChatGateway) -> None:
        self._gateway = gateway

    def list_chats(self, *, session_token: str) -> ChatListScreenData:
        payload = self._gateway.list_chats(session_token=session_token)
        return build_chat_list(payload)

    def load_messages(
        self,
        *,
        session_token: str,
        chat_id: int,
        limit: int = 100,
        offset: int = 0,
    ) -> ChatHistoryScreenData:
        payload = self._gateway.list_messages(
            session_token=session_token,
            chat_id=chat_id,
            limit=limit,
            offset=offset,
        )
        return build_chat_history(payload, chat_id=chat_id)

    def send_text(
        self,
        *,
        session_token: str,
        chat_id: int,
        body_text: str,
        client_message_id: str | None = None,
    ) -> ChatSendResult:
        payload = self._gateway.send_message(
            session_token=session_token,
            chat_id=chat_id,
            body_text=body_text,
            client_message_id=client_message_id,
        )
        return parse_send_result(payload)
