from __future__ import annotations

import os
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Mapping

from firmware.common.protocol.codec import make_envelope
from firmware.common.protocol.constants import EndpointKind, MessageType

from .chat_command_map import CHAT_INTEGRATION_COMMANDS, CHAT_INTEGRATION_WEBSOCKET_PATHS, command_path_set


class TestClientCommandSender:
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
    project_root = Path(__file__).resolve().parents[2]
    server_root = project_root / "server"

    db_name = f"local_chat_chat_e2e_{uuid.uuid4().hex}.db"
    os.environ["LCS_PROFILE"] = "test"
    os.environ["LCS_DATABASE_URL"] = f"sqlite:///data/sqlite/{db_name}"
    os.environ["LCS_STORAGE_ROOT"] = "data"
    os.environ["LCS_RELOAD"] = "false"

    if str(server_root) not in sys.path:
        sys.path.insert(0, str(server_root))

    from fastapi.testclient import TestClient  # type: ignore
    from app.config import get_settings  # type: ignore
    from app.main import create_app  # type: ignore
    from app.models import ChatMessage  # type: ignore
    from app.realtime import chat_protocol_event_payload  # type: ignore
    from app.services.auth import hash_password  # type: ignore

    get_settings(refresh=True)
    app = create_app()

    with TestClient(app) as client:
        route_map: dict[str, set[str]] = {}
        websocket_paths: set[str] = set()
        for route in app.routes:
            path = str(getattr(route, "path", ""))
            if path:
                methods = {item.upper() for item in getattr(route, "methods", set())}
                if methods:
                    existing = route_map.get(path)
                    if existing is None:
                        existing = set()
                        route_map[path] = existing
                    existing.update(methods)
                if not methods and getattr(route, "endpoint", None) is not None:
                    if path.startswith("/realtime/"):
                        websocket_paths.add(path)
        _verify_command_map(route_map=route_map, websocket_paths=websocket_paths)

        _seed_users(db_path=app.state.data_layer.database_path, hash_password=hash_password)
        sender = TestClientCommandSender(client)

        web_token = _login(sender, login="chat-web-user", password="chat-web-secret", client_kind="web")
        device_token = _login(sender, login="chat-device-user", password="chat-device-secret", client_kind="device")

        web_chat_id = _select_common_chat(sender, session_token=web_token)
        device_chat_id = _select_common_chat(sender, session_token=device_token)
        if web_chat_id != device_chat_id:
            raise RuntimeError("web and device flows resolved different chat_id")

        ws_path = f"/realtime/chat/{web_chat_id}?session_token={web_token}"
        with client.websocket_connect(ws_path) as websocket:
            connected = websocket.receive_json()
            if connected.get("type") != "realtime.connected":
                raise RuntimeError(f"expected realtime.connected event, got: {connected}")

            send_payload = sender.send(
                method="POST",
                path=f"/chat/api/chats/{web_chat_id}/messages",
                json_payload={
                    "session_token": device_token,
                    "body_text": "device to web e2e message",
                    "client_message_id": "dev-chat-e2e-01",
                },
            )

            ws_event = websocket.receive_json()

        if send_payload.get("status") != "ok":
            raise RuntimeError("device send flow returned non-ok status")
        if ws_event.get("type") != "chat.message":
            raise RuntimeError(f"expected chat.message realtime event, got: {ws_event}")

        sent_message = _payload_mapping(send_payload.get("message"))
        ws_message = _payload_mapping(_payload_mapping(ws_event).get("message"))

        sent_message_id = _required_int(sent_message, "message_id")
        if _required_int(ws_message, "message_id") != sent_message_id:
            raise RuntimeError("realtime payload message_id mismatch")

        message_model = ChatMessage(
            message_id=sent_message_id,
            chat_id=_required_int(sent_message, "chat_id"),
            author_user_id=_required_int(sent_message, "author_user_id"),
            body_text=_required_str(sent_message, "body_text"),
            client_message_id=_optional_str(sent_message.get("client_message_id")),
            created_at_ms=_required_int(sent_message, "created_at_ms"),
            edited_at_ms=_optional_int(sent_message.get("edited_at_ms")),
        )
        protocol_payload = chat_protocol_event_payload(message_model)

        envelope = make_envelope(
            message_type=MessageType.CHAT_MESSAGE_EVENT,
            sender_kind=EndpointKind.SERVER,
            sender_id="main",
            target_kind=EndpointKind.DEVICE,
            target_id="device-chat-e2e",
            sent_at_ms=message_model.created_at_ms,
            payload=protocol_payload,
            correlation_id=f"web-message-{message_model.message_id}",
        )

        web_history = sender.send(
            method="GET",
            path=f"/chat/api/chats/{web_chat_id}/messages",
            query={"session_token": web_token, "limit": "50", "offset": "0"},
        )
        device_history = sender.send(
            method="GET",
            path=f"/chat/api/chats/{web_chat_id}/messages",
            query={"session_token": device_token, "limit": "50", "offset": "0"},
        )

        web_items = _payload_list(web_history.get("items"))
        device_items = _payload_list(device_history.get("items"))
        if not any(_required_int(item, "message_id") == sent_message_id for item in web_items):
            raise RuntimeError("sent message not visible in web chat history")
        if not any(_required_int(item, "message_id") == sent_message_id for item in device_items):
            raise RuntimeError("sent message not visible in device chat history")

        if str(ws_message.get("chat_id")) != str(protocol_payload.get("chat_id")):
            raise RuntimeError("chat_id mismatch between web and protocol payload")
        if str(ws_message.get("author_user_id")) != str(protocol_payload.get("author_user_id")):
            raise RuntimeError("author_user_id mismatch between web and protocol payload")
        if str(ws_message.get("body_text")) != str(protocol_payload.get("text")):
            raise RuntimeError("text/body mapping mismatch between web and protocol payload")
        if _required_int(ws_message, "created_at_ms") != _required_int(protocol_payload, "created_at_ms"):
            raise RuntimeError("created_at_ms mismatch between web and protocol payload")

        print("CHAT_INTEGRATION_COMMAND_MAP_COUNT", len(CHAT_INTEGRATION_COMMANDS))
        print("CHAT_INTEGRATION_PATHS", sorted(command_path_set()))
        print("CHAT_ID", web_chat_id)
        print("SENT_MESSAGE_ID", sent_message_id)
        print("REALTIME_EVENT_TYPE", ws_event.get("type"))
        print("PROTOCOL_MESSAGE_TYPE", envelope.message_type)
        print("PARITY_TEXT", ws_message.get("body_text"), protocol_payload.get("text"))
        print("WEB_HISTORY_COUNT", web_history.get("count"))
        print("DEVICE_HISTORY_COUNT", device_history.get("count"))


def _verify_command_map(*, route_map: dict[str, set[str]], websocket_paths: set[str]) -> None:
    for command in CHAT_INTEGRATION_COMMANDS:
        methods = route_map.get(command.path_template)
        if methods is None:
            raise RuntimeError(f"missing server route for integration command: {command.path_template}")
        if command.method.upper() not in methods:
            raise RuntimeError(
                f"method mismatch for route {command.path_template}: expected {command.method}, actual {sorted(methods)}"
            )

    missing_ws = sorted(path for path in CHAT_INTEGRATION_WEBSOCKET_PATHS if path not in websocket_paths)
    if missing_ws:
        raise RuntimeError(f"missing websocket routes for chat integration: {missing_ws}")


def _seed_users(*, db_path: Path, hash_password: Any) -> None:
    now_ms = int(time.time() * 1000)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        INSERT INTO users(login, password_hash, role, status, created_at_ms, updated_at_ms)
        VALUES (?, ?, 'user', 'active', ?, ?)
        """,
        ("chat-web-user", hash_password("chat-web-secret"), now_ms, now_ms),
    )
    conn.execute(
        """
        INSERT INTO users(login, password_hash, role, status, created_at_ms, updated_at_ms)
        VALUES (?, ?, 'user', 'active', ?, ?)
        """,
        ("chat-device-user", hash_password("chat-device-secret"), now_ms + 1, now_ms + 1),
    )
    conn.commit()
    conn.close()


def _login(sender: TestClientCommandSender, *, login: str, password: str, client_kind: str) -> str:
    payload = sender.send(
        method="POST",
        path="/auth/login",
        json_payload={"login": login, "password": password, "client_kind": client_kind},
    )
    session = _payload_mapping(payload.get("session"))
    token = str(session.get("token", "")).strip()
    if not token:
        raise RuntimeError("login response does not contain session token")
    return token


def _select_common_chat(sender: TestClientCommandSender, *, session_token: str) -> int:
    payload = sender.send(
        method="GET",
        path="/chat/api/chats",
        query={"session_token": session_token},
    )
    items = _payload_list(payload.get("items"))
    if not items:
        raise RuntimeError("chat list is empty")
    for item in items:
        if str(item.get("kind", "")) == "common":
            return _required_int(item, "chat_id")
    return _required_int(items[0], "chat_id")


def _payload_mapping(value: object) -> dict[str, object]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _payload_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, object]] = []
    for item in value:
        if isinstance(item, Mapping):
            result.append(dict(item))
    return result


def _required_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool):
        raise RuntimeError(f"{key} must be int")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError as exc:
            raise RuntimeError(f"{key} must be int-like") from exc
    raise RuntimeError(f"{key} must be int")


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise RuntimeError("optional int must not be bool")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError as exc:
            raise RuntimeError("optional int must be int-like") from exc
    raise RuntimeError("optional int must be int-like")


def _required_str(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if isinstance(value, str):
        return value
    raise RuntimeError(f"{key} must be str")


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    raise RuntimeError("optional str must be str")


if __name__ == "__main__":
    main()
