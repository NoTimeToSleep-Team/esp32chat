from __future__ import annotations

import os
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Mapping

from .command_map import M5CARDPUTER_CONSOLE_CHAT_COMMANDS, chat_command_path_set
from ..config import M5CardputerConsoleConfig
from ..controller import M5CardputerConsoleController
from ..server_api import CommandSender, ConsoleAuthGateway


class TestClientCommandSender(CommandSender):
    def __init__(self, client: Any) -> None:
        self._client = client

    def send(
        self,
        *,
        method: str,
        path: str,
        query: Mapping[str, str] | None = None,
        json_payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_method = method.upper()
        if normalized_method == "GET":
            response = self._client.get(path, params=dict(query or {}))
        elif normalized_method == "POST":
            response = self._client.post(path, params=dict(query or {}), json=dict(json_payload or {}))
        else:
            raise RuntimeError(f"unsupported method in test sender: {method}")

        payload = response.json()
        if response.status_code >= 400:
            raise RuntimeError(f"HTTP {response.status_code} for {method} {path}: {payload}")
        if not isinstance(payload, dict):
            raise RuntimeError("response payload must be object")
        return payload


def main() -> None:
    project_root = Path(__file__).resolve().parents[4]
    server_root = project_root / "server"

    db_name = f"local_chat_m5cardputer_chat_test_{uuid.uuid4().hex}.db"
    os.environ["LCS_PROFILE"] = "test"
    os.environ["LCS_DATABASE_URL"] = f"sqlite:///data/sqlite/{db_name}"
    os.environ["LCS_STORAGE_ROOT"] = "data"
    os.environ["LCS_RELOAD"] = "false"

    if str(server_root) not in sys.path:
        sys.path.insert(0, str(server_root))

    from fastapi.testclient import TestClient  # type: ignore
    from app.config import get_settings  # type: ignore
    from app.main import create_app  # type: ignore
    from app.services.auth import hash_password  # type: ignore

    get_settings(refresh=True)
    app = create_app()

    with TestClient(app) as client:
        route_map: dict[str, set[str]] = {}
        for route in app.routes:
            methods = {item.upper() for item in getattr(route, "methods", set())}
            existing = route_map.get(route.path)
            if existing is None:
                existing = set()
                route_map[route.path] = existing
            existing.update(methods)
        _verify_command_map(route_map)

        db_path = app.state.data_layer.database_path
        now_ms = int(time.time() * 1000)
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            """
            INSERT INTO users(login, password_hash, role, status, created_at_ms, updated_at_ms)
            VALUES (?, ?, 'user', 'active', ?, ?)
            """,
            (
                "console-chat-user",
                hash_password("console-chat-secret"),
                now_ms,
                now_ms,
            ),
        )
        conn.commit()
        conn.close()

        sender = TestClientCommandSender(client)
        auth_gateway = ConsoleAuthGateway(sender)
        controller = M5CardputerConsoleController(
            config=M5CardputerConsoleConfig(client_kind="device"),
            gateway=auth_gateway,
        )

        controller.start_shell(now_ms=6101)
        shell = controller.secure_login(
            login="console-chat-user",
            password="console-chat-secret",
            now_ms=6102,
        )
        if shell.session is None:
            raise RuntimeError("secure_login did not return session")
        token = shell.session.token

        chats = controller.chat.list_chats(session_token=token)
        target = _select_chat(chats.items)
        history_before = controller.chat.load_messages(
            session_token=token,
            chat_id=target.chat_id,
            limit=100,
        )
        sent = controller.chat.send_text(
            session_token=token,
            chat_id=target.chat_id,
            body_text="m5cardputer console chat verification message",
            client_message_id="console-chat-verify-1",
        )
        history_after = controller.chat.load_messages(
            session_token=token,
            chat_id=target.chat_id,
            limit=100,
        )

        print("COMMAND_MAP_COUNT", len(M5CARDPUTER_CONSOLE_CHAT_COMMANDS))
        print("COMMAND_PATHS", sorted(chat_command_path_set()))
        print("CHAT_COUNT", chats.count)
        print("TARGET_CHAT", target.chat_id, target.kind, target.title)
        print("HISTORY_BEFORE", history_before.count)
        print("SENT_MESSAGE", sent.message.message_id, sent.message.chat_id)
        print("DELIVERED_TO", sent.delivered_to)
        print("HISTORY_AFTER", history_after.count)

        if chats.count < 1:
            raise RuntimeError("chat list is empty")
        if sent.message.chat_id != target.chat_id:
            raise RuntimeError("sent message chat_id mismatch")
        if "verification message" not in sent.message.body_text:
            raise RuntimeError("sent message body mismatch")
        if not any(item.message_id == sent.message.message_id for item in history_after.items):
            raise RuntimeError("sent message is not visible in chat history")


def _verify_command_map(route_map: dict[str, set[str]]) -> None:
    for command in M5CARDPUTER_CONSOLE_CHAT_COMMANDS:
        methods = route_map.get(command.path_template)
        if methods is None:
            raise RuntimeError(f"missing server route for command: {command.path_template}")
        if command.method.upper() not in methods:
            raise RuntimeError(
                f"method mismatch for route {command.path_template}: expected {command.method}, actual {sorted(methods)}"
            )

    forbidden_paths = {
        "/chat/api/private",
        "/chat/api/private/{chat_id}/join",
        "/chat/api/private/{chat_id}/config",
        "/blog/api/posts",
    }
    overlap = sorted(forbidden_paths & chat_command_path_set())
    if overlap:
        raise RuntimeError(f"console chat command map must stay text-chat only: {overlap}")


def _select_chat(items: tuple[Any, ...]) -> Any:
    if not items:
        raise RuntimeError("chat list is empty")
    for item in items:
        if getattr(item, "kind", "") == "common":
            return item
    return items[0]


if __name__ == "__main__":
    main()
