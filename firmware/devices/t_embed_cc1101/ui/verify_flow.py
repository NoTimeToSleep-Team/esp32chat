from __future__ import annotations

import os
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Mapping

from ..config import TEmbedCC1101Config
from ..server_api import CommandSender
from .command_map import T_EMBED_CC1101_CLIENT_COMMANDS, command_path_set
from .controller import TEmbedCC1101ClientController


class FlakyRecordingTestClientSender(CommandSender):
    def __init__(self, client: Any, *, fail_client_message_id: str) -> None:
        self._client = client
        self._fail_client_message_id = fail_client_message_id
        self._failure_sent = False
        self._calls: list[dict[str, Any]] = []

    @property
    def calls(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._calls)

    def send(
        self,
        *,
        method: str,
        path: str,
        query: Mapping[str, str] | None = None,
        json_payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_method = method.upper()
        params = dict(query or {})
        body = dict(json_payload or {})
        self._calls.append(
            {
                "method": normalized_method,
                "path": path,
                "query": dict(params),
                "json_payload": dict(body),
            }
        )

        if (
            not self._failure_sent
            and normalized_method == "POST"
            and path.startswith("/chat/api/chats/")
            and path.endswith("/messages")
            and body.get("client_message_id") == self._fail_client_message_id
        ):
            self._failure_sent = True
            raise RuntimeError("simulated transport error for local buffer test")

        if normalized_method == "GET":
            response = self._client.get(path, params=params)
        elif normalized_method == "POST":
            response = self._client.post(path, params=params, json=body)
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

    db_name = f"local_chat_t_embed_client_flow_{uuid.uuid4().hex}.db"
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
                "t-embed-admin",
                hash_password("t-embed-admin-secret"),
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
                "t-embed-client-user",
                hash_password("t-embed-client-secret"),
                now_ms + 1,
                now_ms + 1,
            ),
        )
        conn.commit()
        conn.close()

        admin_login = client.post(
            "/auth/login",
            json={
                "login": "t-embed-admin",
                "password": "t-embed-admin-secret",
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
                "title": "T-Embed MVP Blog Post",
                "body_text": "Published for t-embed client verification",
            },
        )
        if published.status_code != 200:
            raise RuntimeError(f"blog publish failed: {published.status_code} {published.text}")
        expected_post_id = int(published.json()["post"]["post_id"])

        sender = FlakyRecordingTestClientSender(client, fail_client_message_id="t-embed-buffer-001")
        controller = TEmbedCC1101ClientController(
            config=TEmbedCC1101Config(profile_id="t_embed_cc1101", client_kind="device"),
            sender=sender,
        )

        session = controller.secure_login(
            login="t-embed-client-user",
            password="t-embed-client-secret",
        )
        session_probe = sender.send(
            method="GET",
            path=f"/auth/session/{session.session_token}",
            query={"client_kind": "device"},
        )
        templates = controller.list_templates()
        selected_template = _select_template_id(templates.items)
        chats = controller.list_chats()
        target_chat = _select_chat(chats.items)
        history_before = controller.load_messages(chat_id=target_chat.chat_id)
        sent_template = controller.send_template(
            chat_id=target_chat.chat_id,
            template_id=selected_template,
            client_message_id="t-embed-template-001",
            now_ms=9401,
        )
        buffered = controller.send_text(
            chat_id=target_chat.chat_id,
            body_text="Buffer this text once",
            client_message_id="t-embed-buffer-001",
            now_ms=9402,
        )
        buffer_before_flush = controller.list_buffered()
        flush_result = controller.flush_buffer(limit=10)
        buffer_after_flush = controller.list_buffered()
        history_after = controller.load_messages(chat_id=target_chat.chat_id)
        posts = controller.list_posts(limit=20)
        loaded_post = controller.get_post(post_id=expected_post_id)
        revoked = controller.logout()

        login_kind = _extract_call_value(sender.calls, path="/auth/login", field="client_kind", source="json_payload")
        session_kind = _extract_session_kind(sender.calls)

        print("COMMAND_MAP_COUNT", len(T_EMBED_CC1101_CLIENT_COMMANDS))
        print("COMMAND_PATHS", sorted(command_path_set()))
        print("LOGIN_PROFILE", session.login, session.role, session.access_mode)
        print("TEMPLATES_COUNT", templates.count)
        print("TEMPLATE_SELECTED", selected_template)
        print("CHAT_COUNT", chats.count)
        print("CHAT_TARGET", target_chat.chat_id, target_chat.kind)
        print("HISTORY_BEFORE", history_before.count)
        print("SEND_TEMPLATE", sent_template.status, sent_template.client_message_id)
        print("SEND_BUFFERED", buffered.status, buffered.client_message_id)
        print("BUFFER_BEFORE", buffer_before_flush.count)
        print("BUFFER_FLUSH", flush_result.attempted, flush_result.sent, flush_result.remaining)
        print("BUFFER_AFTER", buffer_after_flush.count)
        print("HISTORY_AFTER", history_after.count)
        print("POSTS_COUNT", posts.count)
        print("LOADED_POST", loaded_post.post_id, loaded_post.title)
        print("LOGOUT_REVOKED", revoked)
        print("LOGIN_CLIENT_KIND", login_kind)
        print("SESSION_CLIENT_KIND", session_kind)
        print("SESSION_PROBE_STATUS", session_probe.get("status"))

        if session.role != "user":
            raise RuntimeError("t-embed login role mismatch")
        if templates.count < 1:
            raise RuntimeError("template list is empty")
        if chats.count < 1:
            raise RuntimeError("chat list is empty")
        if sent_template.status != "sent":
            raise RuntimeError("template send must be delivered")
        if buffered.status != "buffered":
            raise RuntimeError("second send must be buffered after synthetic failure")
        if buffer_before_flush.count != 1:
            raise RuntimeError("buffer must contain one message before flush")
        if flush_result.sent != 1 or flush_result.remaining != 0:
            raise RuntimeError("flush must deliver buffered message")
        if buffer_after_flush.count != 0:
            raise RuntimeError("buffer must be empty after flush")
        if not any(item.client_message_id == "t-embed-template-001" for item in history_after.items):
            raise RuntimeError("template message is not visible in chat history")
        if not any(item.client_message_id == "t-embed-buffer-001" for item in history_after.items):
            raise RuntimeError("buffered message is not visible in chat history after flush")
        if not any(item.post_id == expected_post_id for item in posts.items):
            raise RuntimeError("published blog post is not visible in list")
        if loaded_post.post_id != expected_post_id:
            raise RuntimeError("loaded blog post id mismatch")
        if not revoked:
            raise RuntimeError("logout did not revoke session")
        if login_kind != "device":
            raise RuntimeError(f"secure_login must use device client_kind, got {login_kind}")
        if session_kind != "device":
            raise RuntimeError(f"session check must use device client_kind, got {session_kind}")
        if session_probe.get("status") != "ok":
            raise RuntimeError("session probe failed")


def _verify_command_map(route_map: dict[str, set[str]]) -> None:
    for command in T_EMBED_CC1101_CLIENT_COMMANDS:
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
        raise RuntimeError(f"t-embed client command map contains forbidden paths: {overlap}")


def _select_chat(items: tuple[Any, ...]) -> Any:
    if not items:
        raise RuntimeError("chat list is empty")
    for item in items:
        if getattr(item, "kind", "") == "common":
            return item
    return items[0]


def _select_template_id(items: tuple[Any, ...]) -> str:
    if not items:
        raise RuntimeError("template list is empty")
    first = items[0]
    template_id = getattr(first, "template_id", None)
    if not isinstance(template_id, str) or not template_id:
        raise RuntimeError("template entry must have non-empty template_id")
    return template_id


def _extract_call_value(
    calls: tuple[dict[str, Any], ...],
    *,
    path: str,
    field: str,
    source: str,
) -> str | None:
    for call in calls:
        if call.get("path") != path:
            continue
        payload = call.get(source)
        if not isinstance(payload, Mapping):
            continue
        value = payload.get(field)
        if isinstance(value, str):
            return value
    return None


def _extract_session_kind(calls: tuple[dict[str, Any], ...]) -> str | None:
    for call in calls:
        path = call.get("path")
        if not isinstance(path, str) or not path.startswith("/auth/session/"):
            continue
        query = call.get("query")
        if not isinstance(query, Mapping):
            continue
        value = query.get("client_kind")
        if isinstance(value, str):
            return value
    return None


if __name__ == "__main__":
    main()
