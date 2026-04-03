from __future__ import annotations

import os
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Mapping

from ..config import FlipperZeroConfig
from ..models import ConnectionState
from ..server_api import CommandSender
from ..shell import StaticCapabilityDetector
from .command_map import FLIPPER_ZERO_CLIENT_COMMANDS, command_path_set
from .controller import FlipperZeroLimitedClientController


class RecordingTestClientSender(CommandSender):
    def __init__(self, client: Any) -> None:
        self._client = client
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

    db_name = f"local_chat_flipper_client_flow_{uuid.uuid4().hex}.db"
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
                "flipper-admin",
                hash_password("flipper-admin-secret"),
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
                "flipper-client-user",
                hash_password("flipper-client-secret"),
                now_ms + 1,
                now_ms + 1,
            ),
        )
        conn.commit()
        conn.close()

        admin_login = client.post(
            "/auth/login",
            json={
                "login": "flipper-admin",
                "password": "flipper-admin-secret",
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
                "title": "Flipper Limited Blog Post",
                "body_text": "Published for flipper limited client verification",
            },
        )
        if published.status_code != 200:
            raise RuntimeError(f"blog publish failed: {published.status_code} {published.text}")
        expected_post_id = int(published.json()["post"]["post_id"])

        sender = RecordingTestClientSender(client)

        limited = FlipperZeroLimitedClientController(
            config=FlipperZeroConfig(profile_id="flipper_zero", client_kind="device"),
            sender=sender,
            capability_detector=StaticCapabilityDetector(wifi_dev_board_attached=False),
        )
        limited_detected = limited.detect_capabilities(now_ms=9801)
        limited_connected = limited.start_shell(now_ms=9802)
        limited_login_error: str | None = None
        try:
            limited.secure_login(
                login="flipper-client-user",
                password="flipper-client-secret",
                now_ms=9803,
            )
        except RuntimeError as exc:
            limited_login_error = str(exc)

        network = FlipperZeroLimitedClientController(
            config=FlipperZeroConfig(profile_id="flipper_zero", client_kind="device"),
            sender=sender,
            capability_detector=StaticCapabilityDetector(wifi_dev_board_attached=True),
        )
        network_detected = network.detect_capabilities(now_ms=9811)
        network_connected = network.start_shell(now_ms=9812)
        logged_in = network.secure_login(
            login="flipper-client-user",
            password="flipper-client-secret",
            now_ms=9813,
        )
        if logged_in.session is None:
            raise RuntimeError("secure_login did not create session")
        resumed = network.resume_session(session_token=logged_in.session.token, now_ms=9814)
        mode_payload = network.read_mode()
        chats = network.list_chats()
        target_chat = _select_chat(chats.items)
        history_before = network.load_messages(chat_id=target_chat.chat_id)
        sent = network.send_text(
            chat_id=target_chat.chat_id,
            body_text="flipper limited text message",
            client_message_id="flipper-msg-1",
        )
        history_after = network.load_messages(chat_id=target_chat.chat_id)
        posts = network.list_posts(limit=20)
        loaded_post = network.get_post(post_id=expected_post_id)
        logged_out = network.logout(now_ms=9815)

        login_kind = _extract_call_value(sender.calls, path="/auth/login", field="client_kind", source="json_payload")
        session_kind = _extract_session_kind(sender.calls)
        has_health_call = _has_call(sender.calls, path="/health", method="GET")

        print("COMMAND_MAP_COUNT", len(FLIPPER_ZERO_CLIENT_COMMANDS))
        print("COMMAND_PATHS", sorted(command_path_set()))
        print("LIMITED_MODE", limited_detected.connection_state.value, limited_detected.capability.mode)
        print("LIMITED_CONNECT", limited_connected.connection_state.value, limited_connected.connected)
        print("LIMITED_LOGIN_ERROR", limited_login_error)
        print("NETWORK_MODE", network_detected.connection_state.value, network_detected.capability.mode)
        print("NETWORK_CONNECTED", network_connected.connection_state.value, network_connected.connected)
        print("LOGIN_ROLE", logged_in.session.role)
        print("RESUME_STATE", resumed.connection_state.value)
        print("MODE_ACCESS", mode_payload.get("access_mode"))
        print("CHAT_COUNT", chats.count)
        print("CHAT_TARGET", target_chat.chat_id, target_chat.kind)
        print("HISTORY_BEFORE", history_before.count)
        print("SENT_MESSAGE", sent.message.message_id, sent.message.chat_id)
        print("HISTORY_AFTER", history_after.count)
        print("POSTS_COUNT", posts.count)
        print("LOADED_POST", loaded_post.post_id, loaded_post.title)
        print("LOGOUT_STATE", logged_out.connection_state.value, logged_out.session is None)
        print("LOGIN_CLIENT_KIND", login_kind)
        print("SESSION_CLIENT_KIND", session_kind)
        print("HAS_HEALTH_CALL", has_health_call)

        if limited_detected.connection_state != ConnectionState.LIMITED:
            raise RuntimeError("limited detection did not switch to limited mode")
        if limited_connected.connection_state != ConnectionState.LIMITED:
            raise RuntimeError("start_shell must stay limited without wifi dev board")
        if limited_login_error is None or "limited mode" not in limited_login_error:
            raise RuntimeError("secure_login must fail in limited mode")
        if network_detected.connection_state != ConnectionState.DISCONNECTED:
            raise RuntimeError("network detection must remain disconnected before connect")
        if network_connected.connection_state != ConnectionState.CONNECTED:
            raise RuntimeError("network shell did not connect")
        if logged_in.session.role != "user":
            raise RuntimeError("flipper login role mismatch")
        if resumed.connection_state != ConnectionState.AUTHENTICATED:
            raise RuntimeError("resume_session did not restore authenticated state")
        if mode_payload.get("status") != "ok":
            raise RuntimeError("mode read failed")
        if chats.count < 1:
            raise RuntimeError("chat list is empty")
        if sent.message.chat_id != target_chat.chat_id:
            raise RuntimeError("sent message chat mismatch")
        if not any(item.message_id == sent.message.message_id for item in history_after.items):
            raise RuntimeError("sent message is not visible in history")
        if not any(item.post_id == expected_post_id for item in posts.items):
            raise RuntimeError("published blog post is not visible in list")
        if loaded_post.post_id != expected_post_id:
            raise RuntimeError("loaded blog post id mismatch")
        if logged_out.session is not None:
            raise RuntimeError("logout did not clear session")
        if login_kind != "device":
            raise RuntimeError(f"secure_login must use device client_kind, got {login_kind}")
        if session_kind != "device":
            raise RuntimeError(f"session check must use device client_kind, got {session_kind}")
        if not has_health_call:
            raise RuntimeError("network flow must include health probe")


def _verify_command_map(route_map: dict[str, set[str]]) -> None:
    for command in FLIPPER_ZERO_CLIENT_COMMANDS:
        methods = route_map.get(command.path_template)
        if methods is None:
            raise RuntimeError(f"missing server route for command: {command.path_template}")
        if command.method.upper() not in methods:
            raise RuntimeError(
                f"method mismatch for route {command.path_template}: expected {command.method}, actual {sorted(methods)}"
            )

    forbidden_paths = {
        "/auth/guest",
        "/chat/api/upload",
        "/blog/api/upload",
        "/rfid/api/cards",
        "/ops/api/degraded-mode",
    }
    overlap = sorted(forbidden_paths & command_path_set())
    if overlap:
        raise RuntimeError(f"flipper client command map contains forbidden paths: {overlap}")


def _select_chat(items: tuple[Any, ...]) -> Any:
    if not items:
        raise RuntimeError("chat list is empty")
    for item in items:
        if getattr(item, "kind", "") == "common":
            return item
    return items[0]


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


def _has_call(calls: tuple[dict[str, Any], ...], *, path: str, method: str) -> bool:
    expected_method = method.upper()
    for call in calls:
        if call.get("path") != path:
            continue
        if call.get("method") == expected_method:
            return True
    return False


if __name__ == "__main__":
    main()
