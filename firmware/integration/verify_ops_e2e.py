from __future__ import annotations

import os
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Mapping

from .ops_command_map import OPS_INTEGRATION_COMMANDS, command_path_set


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

    db_name = f"local_chat_ops_e2e_{uuid.uuid4().hex}.db"
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

        _seed_users(db_path=app.state.data_layer.database_path, hash_password=hash_password)
        sender = TestClientCommandSender(client)

        admin_token = _login(sender, login="ops-admin", password="ops-admin-secret", client_kind="web")
        device_token = _login(sender, login="ops-device-user", password="ops-device-secret", client_kind="device")

        blog_publish_payload = sender.send(
            method="POST",
            path="/admin/content/blog/posts",
            json_payload={
                "session_token": admin_token,
                "title": "Ops Integration Blog Post",
                "body_text": "Published by admin and read by device flow",
            },
        )
        published_post = _payload_mapping(blog_publish_payload.get("post"))
        published_post_id = _required_int(published_post, "post_id")

        device_blog_list = sender.send(
            method="GET",
            path="/blog/api/posts",
            query={"session_token": device_token, "limit": "20", "offset": "0"},
        )
        if not any(_required_int(item, "post_id") == published_post_id for item in _payload_list(device_blog_list.get("items"))):
            raise RuntimeError("published admin blog post not visible in device flow")

        device_blog_get = sender.send(
            method="GET",
            path=f"/blog/api/posts/{published_post_id}",
            query={"session_token": device_token},
        )
        read_post = _payload_mapping(device_blog_get.get("post"))
        if _required_int(read_post, "post_id") != published_post_id:
            raise RuntimeError("device blog read post_id mismatch")

        support_create = sender.send(
            method="POST",
            path="/support/api/tickets",
            json_payload={
                "session_token": device_token,
                "title": "Device Support Ticket",
                "body_text": "Need help with local integration behavior",
            },
        )
        support_ticket = _payload_mapping(support_create.get("ticket"))
        ticket_id = _required_int(support_ticket, "ticket_id")

        admin_ticket_list = sender.send(
            method="GET",
            path="/admin/content/support/tickets",
            query={"session_token": admin_token, "limit": "50", "offset": "0"},
        )
        if not any(_required_int(item, "ticket_id") == ticket_id for item in _payload_list(admin_ticket_list.get("items"))):
            raise RuntimeError("device-created support ticket not visible in admin queue")

        admin_reply = sender.send(
            method="POST",
            path=f"/admin/content/support/tickets/{ticket_id}/reply",
            json_payload={
                "session_token": admin_token,
                "body_text": "Acknowledged, issue reproduced and tracked",
            },
        )
        reply_message = _payload_mapping(admin_reply.get("message"))
        reply_message_id = _required_int(reply_message, "message_id")

        admin_status_update = sender.send(
            method="POST",
            path=f"/admin/content/support/tickets/{ticket_id}/status",
            json_payload={
                "session_token": admin_token,
                "status": "resolved",
            },
        )
        updated_ticket = _payload_mapping(admin_status_update.get("ticket"))
        if str(updated_ticket.get("status", "")) != "resolved":
            raise RuntimeError("admin support status update mismatch")

        device_messages = sender.send(
            method="GET",
            path=f"/support/api/tickets/{ticket_id}/messages",
            query={"session_token": device_token, "limit": "50", "offset": "0"},
        )
        if not any(_required_int(item, "message_id") == reply_message_id for item in _payload_list(device_messages.get("items"))):
            raise RuntimeError("admin support reply not visible in device user thread")

        device_tickets = sender.send(
            method="GET",
            path="/support/api/tickets",
            query={"session_token": device_token, "limit": "20", "offset": "0"},
        )
        resolved_ticket_items = [
            item
            for item in _payload_list(device_tickets.get("items"))
            if _required_int(item, "ticket_id") == ticket_id
        ]
        if not resolved_ticket_items:
            raise RuntimeError("device support ticket not visible in user ticket list")
        if str(resolved_ticket_items[0].get("status", "")) != "resolved":
            raise RuntimeError("resolved status not visible for device support ticket")

        print("OPS_INTEGRATION_COMMAND_MAP_COUNT", len(OPS_INTEGRATION_COMMANDS))
        print("OPS_INTEGRATION_PATHS", sorted(command_path_set()))
        print("BLOG_POST_ID", published_post_id)
        print("SUPPORT_TICKET_ID", ticket_id)
        print("SUPPORT_REPLY_ID", reply_message_id)
        print("SUPPORT_FINAL_STATUS", resolved_ticket_items[0].get("status"))


def _verify_command_map(route_map: dict[str, set[str]]) -> None:
    for command in OPS_INTEGRATION_COMMANDS:
        methods = route_map.get(command.path_template)
        if methods is None:
            raise RuntimeError(f"missing server route for integration command: {command.path_template}")
        if command.method.upper() not in methods:
            raise RuntimeError(
                f"method mismatch for route {command.path_template}: expected {command.method}, actual {sorted(methods)}"
            )


def _seed_users(*, db_path: Path, hash_password: Any) -> None:
    now_ms = int(time.time() * 1000)
    connection = sqlite3.connect(str(db_path))
    connection.execute(
        """
        INSERT INTO users(login, password_hash, role, status, created_at_ms, updated_at_ms)
        VALUES (?, ?, 'admin', 'active', ?, ?)
        """,
        ("ops-admin", hash_password("ops-admin-secret"), now_ms, now_ms),
    )
    connection.execute(
        """
        INSERT INTO users(login, password_hash, role, status, created_at_ms, updated_at_ms)
        VALUES (?, ?, 'user', 'active', ?, ?)
        """,
        ("ops-device-user", hash_password("ops-device-secret"), now_ms + 1, now_ms + 1),
    )
    connection.commit()
    connection.close()


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


def _payload_mapping(value: object) -> dict[str, object]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _payload_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    items: list[dict[str, object]] = []
    for item in value:
        if isinstance(item, Mapping):
            items.append(dict(item))
    return items


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


if __name__ == "__main__":
    main()
