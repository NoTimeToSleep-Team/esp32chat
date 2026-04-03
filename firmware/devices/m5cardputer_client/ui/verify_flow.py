from __future__ import annotations

import os
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Mapping

from firmware.devices.m5cardputer_console.server_api import CommandSender

from ..command_map import M5CARDPUTER_HANDHELD_COMMANDS, command_path_set
from ..config import M5CardputerClientConfig
from .controller import M5CardputerHandheldClientController


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

    db_name = f"local_chat_m5cardputer_client_flow_{uuid.uuid4().hex}.db"
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
            VALUES (?, ?, 'admin', 'active', ?, ?)
            """,
            (
                "external-client-admin",
                hash_password("external-client-admin-secret"),
                now_ms,
                now_ms,
            ),
        )
        conn.execute(
            """
            INSERT INTO users(login, password_hash, role, status, created_at_ms, updated_at_ms)
            VALUES (?, ?, 'user', 'active', ?, ?)
            """,
            (
                "external-client-user",
                hash_password("external-client-user-secret"),
                now_ms + 1,
                now_ms + 1,
            ),
        )
        conn.commit()
        conn.close()

        admin_login = client.post(
            "/auth/login",
            json={
                "login": "external-client-admin",
                "password": "external-client-admin-secret",
                "client_kind": "web",
            },
        )
        if admin_login.status_code != 200:
            raise RuntimeError(f"admin login failed: {admin_login.status_code} {admin_login.text}")
        admin_token = admin_login.json()["session"]["token"]

        published = client.post(
            "/admin/content/blog/posts",
            json={
                "session_token": admin_token,
                "title": "External Handheld Blog Post",
                "body_text": "Published for handheld client verification",
            },
        )
        if published.status_code != 200:
            raise RuntimeError(f"blog publish failed: {published.status_code} {published.text}")
        expected_post_id = int(published.json()["post"]["post_id"])

        sender = TestClientCommandSender(client)
        controller = M5CardputerHandheldClientController(
            config=M5CardputerClientConfig(profile_id="m5cardputer_client", client_kind="device"),
            sender=sender,
        )

        session = controller.secure_login(
            login="external-client-user",
            password="external-client-user-secret",
        )
        chats = controller.list_chats()
        target_chat = _select_chat(chats.items)
        history_before = controller.load_messages(chat_id=target_chat.chat_id)
        sent = controller.send_text(
            chat_id=target_chat.chat_id,
            body_text="external handheld text message",
            client_message_id="external-client-msg-1",
        )
        history_after = controller.load_messages(chat_id=target_chat.chat_id)
        posts = controller.list_posts(limit=20)
        loaded_post = controller.get_post(post_id=expected_post_id)
        revoked = controller.logout()

        print("COMMAND_MAP_COUNT", len(M5CARDPUTER_HANDHELD_COMMANDS))
        print("COMMAND_PATHS", sorted(command_path_set()))
        print("LOGIN_PROFILE", session.login, session.role, session.access_mode)
        print("CHAT_COUNT", chats.count)
        print("CHAT_TARGET", target_chat.chat_id, target_chat.kind)
        print("HISTORY_BEFORE", history_before.count)
        print("SENT_MESSAGE", sent.message.message_id, sent.message.chat_id)
        print("HISTORY_AFTER", history_after.count)
        print("POSTS_COUNT", posts.count)
        print("LOADED_POST", loaded_post.post_id, loaded_post.title)
        print("LOGOUT_REVOKED", revoked)

        if session.role != "user":
            raise RuntimeError("handheld login role mismatch")
        if chats.count < 1:
            raise RuntimeError("chat list is empty")
        if sent.message.chat_id != target_chat.chat_id:
            raise RuntimeError("sent message chat mismatch")
        if not any(item.message_id == sent.message.message_id for item in history_after.items):
            raise RuntimeError("sent message is not visible in chat history")
        if not any(item.post_id == expected_post_id for item in posts.items):
            raise RuntimeError("published blog post is not visible in list")
        if loaded_post.post_id != expected_post_id:
            raise RuntimeError("loaded blog post id mismatch")
        if not revoked:
            raise RuntimeError("logout did not revoke session")


def _verify_command_map(route_map: dict[str, set[str]]) -> None:
    for command in M5CARDPUTER_HANDHELD_COMMANDS:
        methods = route_map.get(command.path_template)
        if methods is None:
            raise RuntimeError(f"missing server route for command: {command.path_template}")
        if command.method.upper() not in methods:
            raise RuntimeError(
                f"method mismatch for route {command.path_template}: expected {command.method}, actual {sorted(methods)}"
            )

    forbidden_paths = {
        "/auth/guest",
        "/ops/api/degraded-mode",
        "/ops/api/shutdown/dry-run",
        "/rfid/api/cards",
    }
    overlap = sorted(forbidden_paths & command_path_set())
    if overlap:
        raise RuntimeError(f"handheld command map contains forbidden paths: {overlap}")


def _select_chat(items: tuple[Any, ...]) -> Any:
    if not items:
        raise RuntimeError("chat list is empty")
    for item in items:
        if getattr(item, "kind", "") == "common":
            return item
    return items[0]


if __name__ == "__main__":
    main()
