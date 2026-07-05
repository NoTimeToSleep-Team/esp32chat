from __future__ import annotations

import os
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Mapping

from .api import AdminUsersGateway
from .command_map import M5TAB_ADMIN_USERS_COMMANDS, admin_users_command_path_set
from .controller import M5TabAdminUsersController


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
            raise RuntimeError(
                f"HTTP {response.status_code} for {method} {path}: {payload}"
            )
        if not isinstance(payload, dict):
            raise RuntimeError("response payload must be object")
        return payload


def main() -> None:
    project_root = Path(__file__).resolve().parents[5]
    server_root = project_root / "server"

    db_name = f"local_chat_m5tab_admin_users_test_{uuid.uuid4().hex}.db"
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
            methods = {method.upper() for method in getattr(route, "methods", set())}
            if route.path not in route_map:
                route_map[route.path] = set()
            route_map[route.path].update(methods)
        _verify_command_map(route_map)

        db_path = app.state.data_layer.database_path
        now_ms = int(time.time() * 1000)
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            """
            INSERT INTO users(login, password_hash, role, status, created_at_ms, updated_at_ms, phone, registration_device_id)
            VALUES (?, ?, 'admin', 'active', ?, ?, NULL, NULL)
            """,
            ("m5tab-users-admin", hash_password("m5tab-users-secret-123"), now_ms, now_ms),
        )
        conn.execute(
            """
            INSERT INTO users(login, password_hash, role, status, created_at_ms, updated_at_ms, phone, registration_device_id)
            VALUES (?, ?, 'user', 'active', ?, ?, ?, ?)
            """,
            (
                "panel-user-a",
                hash_password("panel-user-a-secret"),
                now_ms + 1,
                now_ms + 1,
                "+10000000001",
                "device-panel-a",
            ),
        )
        conn.execute(
            """
            INSERT INTO users(login, password_hash, role, status, created_at_ms, updated_at_ms, phone, registration_device_id)
            VALUES (?, ?, 'user', 'active', ?, ?, ?, ?)
            """,
            (
                "panel-user-b",
                hash_password("panel-user-b-secret"),
                now_ms + 2,
                now_ms + 2,
                "+10000000002",
                "device-panel-b",
            ),
        )
        conn.commit()
        conn.close()

        login = client.post(
            "/auth/login",
            json={
                "login": "m5tab-users-admin",
                "password": "m5tab-users-secret-123",
                "client_kind": "web",
            },
        )
        if login.status_code != 200:
            raise RuntimeError(f"admin login failed: {login.status_code} {login.text}")
        token = login.json()["session"]["token"]

        sender = TestClientCommandSender(client)
        gateway = AdminUsersGateway(sender)
        controller = M5TabAdminUsersController(gateway)

        screen = controller.list_users(session_token=token, limit=50)
        user_a = _find_user(screen.items, login="panel-user-a")
        user_b = _find_user(screen.items, login="panel-user-b")

        banned_user = controller.ban_user(
            session_token=token,
            user_id=user_a.user_id,
            reason="policy violation",
        )
        unbanned_user = controller.unban_user(session_token=token, user_id=user_a.user_id)

        blacklisted_user, blacklist_entry = controller.blacklist_device(
            session_token=token,
            user_id=user_a.user_id,
            reason="compromised device",
        )
        unblacklisted_user = controller.unblacklist_device(
            session_token=token,
            user_id=user_a.user_id,
        )

        deleted = controller.delete_user(session_token=token, user_id=user_b.user_id)
        screen_after = controller.list_users(session_token=token, limit=50)

        print("COMMAND_MAP_COUNT", len(M5TAB_ADMIN_USERS_COMMANDS))
        print("COMMAND_PATHS", sorted(admin_users_command_path_set()))
        print("LIST_COUNT", screen.count)
        print("BAN_STATUS", banned_user.status)
        print("UNBAN_STATUS", unbanned_user.status)
        print("BLACKLISTED", blacklisted_user.device_blacklisted, blacklist_entry.device_id)
        print("UNBLACKLISTED", unblacklisted_user.device_blacklisted)
        print("DELETED", deleted.deleted_user_id, deleted.deleted_login)
        print("POST_DELETE_COUNT", screen_after.count)

        if banned_user.status != "banned":
            raise RuntimeError("ban operation did not set banned status")
        if unbanned_user.status != "active":
            raise RuntimeError("unban operation did not restore active status")
        if not blacklisted_user.device_blacklisted:
            raise RuntimeError("blacklist operation did not mark user device_blacklisted")
        if blacklist_entry.device_id != "device-panel-a":
            raise RuntimeError("blacklist entry device_id mismatch")
        if unblacklisted_user.device_blacklisted:
            raise RuntimeError("unblacklist operation did not clear device_blacklisted flag")
        if deleted.deleted_login != "panel-user-b":
            raise RuntimeError("delete operation returned unexpected login")
        if any(item.login == "panel-user-b" for item in screen_after.items):
            raise RuntimeError("deleted user still present in list")


def _verify_command_map(route_map: dict[str, set[str]]) -> None:
    for command in M5TAB_ADMIN_USERS_COMMANDS:
        methods = route_map.get(command.path_template)
        if methods is None:
            raise RuntimeError(f"missing server route for command: {command.path_template}")
        if command.method.upper() not in methods:
            raise RuntimeError(
                f"method mismatch for route {command.path_template}: expected {command.method}, actual {sorted(methods)}"
            )

    forbidden_paths = {
        "/ops/api/degraded-mode",
        "/ops/api/shutdown/dry-run",
        "/ops/api/backups",
        "/ops/api/backups/dry-run",
        "/rfid/api/cards",
        "/admin/content/blog/publish",
    }
    overlap = sorted(forbidden_paths & admin_users_command_path_set())
    if overlap:
        raise RuntimeError(f"admin users command map must stay user-moderation only: {overlap}")


def _find_user(items: tuple[Any, ...], *, login: str) -> Any:
    for item in items:
        if getattr(item, "login", None) == login:
            return item
    raise RuntimeError(f"user not found in list: {login}")


if __name__ == "__main__":
    main()
