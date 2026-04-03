from __future__ import annotations

import os
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Mapping

from .api import AdminOpsGateway
from .command_map import M5TAB_ADMIN_OPS_COMMANDS, admin_ops_command_path_set
from .controller import M5TabAdminOpsController


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
        elif normalized_method == "DELETE":
            response = self._client.delete(path, params=dict(query or {}))
        else:
            raise RuntimeError(f"unsupported method in test sender: {method}")

        payload = response.json()
        if response.status_code >= 400:
            raise RuntimeError(f"HTTP {response.status_code} for {method} {path}: {payload}")
        if not isinstance(payload, dict):
            raise RuntimeError("response payload must be object")
        return payload


def main() -> None:
    project_root = Path(__file__).resolve().parents[5]
    server_root = project_root / "server"

    db_name = f"local_chat_m5tab_admin_ops_test_{uuid.uuid4().hex}.db"
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
            INSERT INTO users(login, password_hash, role, status, created_at_ms, updated_at_ms, phone, registration_device_id)
            VALUES (?, ?, 'admin', 'active', ?, ?, NULL, NULL)
            """,
            ("m5tab-ops-admin", hash_password("m5tab-ops-admin-secret"), now_ms, now_ms),
        )
        conn.execute(
            """
            INSERT INTO users(login, password_hash, role, status, created_at_ms, updated_at_ms, phone, registration_device_id)
            VALUES (?, ?, 'user', 'active', ?, ?, ?, ?)
            """,
            (
                "m5tab-ops-user",
                hash_password("m5tab-ops-user-secret"),
                now_ms + 1,
                now_ms + 1,
                "+15550000001",
                "device-ops-user",
            ),
        )
        conn.commit()
        conn.close()

        admin_login = client.post(
            "/auth/login",
            json={
                "login": "m5tab-ops-admin",
                "password": "m5tab-ops-admin-secret",
                "client_kind": "web",
            },
        )
        if admin_login.status_code != 200:
            raise RuntimeError(f"admin login failed: {admin_login.status_code} {admin_login.text}")
        admin_token = admin_login.json()["session"]["token"]

        user_login = client.post(
            "/auth/login",
            json={
                "login": "m5tab-ops-user",
                "password": "m5tab-ops-user-secret",
                "client_kind": "web",
            },
        )
        if user_login.status_code != 200:
            raise RuntimeError(f"user login failed: {user_login.status_code} {user_login.text}")
        user_token = user_login.json()["session"]["token"]

        support_create = client.post(
            "/support/api/tickets",
            json={
                "session_token": user_token,
                "title": "Panel test ticket",
                "body_text": "Need help from admin panel",
            },
        )
        if support_create.status_code != 200:
            raise RuntimeError(f"support ticket create failed: {support_create.status_code} {support_create.text}")
        support_ticket_id = int(support_create.json()["ticket"]["ticket_id"])

        sender = TestClientCommandSender(client)
        gateway = AdminOpsGateway(sender)
        controller = M5TabAdminOpsController(gateway)

        tickets = controller.list_support_tickets(session_token=admin_token, limit=20)
        ticket = _find_ticket(tickets.items, support_ticket_id)
        support_reply = controller.reply_support_ticket(
            session_token=admin_token,
            ticket_id=ticket.ticket_id,
            body_text="Admin acknowledged and resolved.",
        )
        updated_ticket = controller.set_support_ticket_status(
            session_token=admin_token,
            ticket_id=ticket.ticket_id,
            status="resolved",
        )

        post = controller.publish_blog_post(
            session_token=admin_token,
            title="Panel Announcement",
            body_text="Maintenance window completed.",
        )
        posts = controller.list_blog_posts(session_token=admin_token, limit=20)

        enrolled = controller.enroll_rfid_card(
            session_token=admin_token,
            card_uid="04A1B2C3D4",
            card_label="Ops Test Card",
            note="panel test",
            is_active=True,
        )
        toggled = controller.set_rfid_card_active(
            session_token=admin_token,
            card_id=enrolled.card_id,
            is_active=False,
        )
        cards = controller.list_rfid_cards(session_token=admin_token, include_inactive=True, limit=20)

        mode_before = controller.get_mode_state(session_token=admin_token)
        target_mode = "closed" if mode_before.access_mode == "open" else "open"
        mode_after = controller.set_mode_with_safe_hold(
            session_token=admin_token,
            access_mode=target_mode,
            hold_seconds=1,
        )

        print("COMMAND_MAP_COUNT", len(M5TAB_ADMIN_OPS_COMMANDS))
        print("COMMAND_PATHS", sorted(admin_ops_command_path_set()))
        print("SUPPORT_COUNT", tickets.count)
        print("SUPPORT_REPLY_ID", support_reply.message_id)
        print("SUPPORT_STATUS", updated_ticket.status)
        print("BLOG_POST_ID", post.post_id)
        print("BLOG_COUNT", posts.count)
        print("RFID_CARD", enrolled.card_id, enrolled.is_active, toggled.is_active, cards.count)
        print("MODE_BEFORE", mode_before.access_mode, mode_before.required_hold_seconds)
        print("MODE_AFTER", mode_after.access_mode, mode_after.required_hold_seconds)
        print("MODE_SEQUENCE", list(mode_after.safe_sequence))

        if not any(item.ticket_id == support_ticket_id for item in tickets.items):
            raise RuntimeError("support ticket is not visible in admin list")
        if updated_ticket.status != "resolved":
            raise RuntimeError("support ticket status not updated to resolved")
        if not any(item.post_id == post.post_id for item in posts.items):
            raise RuntimeError("published blog post is not visible in admin list")
        if toggled.is_active:
            raise RuntimeError("rfid card active flag was not switched off")
        if not any(item.card_id == enrolled.card_id for item in cards.items):
            raise RuntimeError("enrolled rfid card is not visible in list")
        if mode_after.access_mode != target_mode:
            raise RuntimeError("admin mode set did not apply target mode")
        if mode_after.required_hold_seconds < 1:
            raise RuntimeError("admin mode required_hold_seconds invalid")
        if "hold_toggle_button" not in mode_after.safe_sequence:
            raise RuntimeError("safe sequence must contain hold_toggle_button")


def _verify_command_map(route_map: dict[str, set[str]]) -> None:
    for command in M5TAB_ADMIN_OPS_COMMANDS:
        methods = route_map.get(command.path_template)
        if methods is None:
            raise RuntimeError(f"missing server route for command: {command.path_template}")
        if command.method.upper() not in methods:
            raise RuntimeError(
                f"method mismatch for route {command.path_template}: expected {command.method}, actual {sorted(methods)}"
            )

    forbidden_paths = {
        "/ops/api/shutdown/dry-run",
        "/ops/api/backups",
        "/ops/api/backups/dry-run",
        "/ops/api/backups/restore/dry-run",
        "/admin/users/{user_id}/ban",
        "/admin/users/{user_id}/blacklist-device",
    }
    overlap = sorted(forbidden_paths & admin_ops_command_path_set())
    if overlap:
        raise RuntimeError(f"admin ops command map contains forbidden paths: {overlap}")


def _find_ticket(items: tuple[Any, ...], ticket_id: int) -> Any:
    for item in items:
        if int(getattr(item, "ticket_id", -1)) == ticket_id:
            return item
    raise RuntimeError(f"support ticket not found: {ticket_id}")


if __name__ == "__main__":
    main()
