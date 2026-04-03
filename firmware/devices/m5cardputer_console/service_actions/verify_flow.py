from __future__ import annotations

import os
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Mapping

from .command_map import M5CARDPUTER_CONSOLE_SERVICE_COMMANDS, service_command_path_set
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

    db_name = f"local_chat_m5cardputer_service_test_{uuid.uuid4().hex}.db"
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
                "console-service-user",
                hash_password("console-service-secret"),
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

        controller.start_shell(now_ms=8101)
        state = controller.secure_login(
            login="console-service-user",
            password="console-service-secret",
            now_ms=8102,
        )
        if state.session is None:
            raise RuntimeError("secure_login did not return session")
        snapshot = controller.service_actions.refresh_shortcuts(session_token=state.session.token)

        print("COMMAND_MAP_COUNT", len(M5CARDPUTER_CONSOLE_SERVICE_COMMANDS))
        print("COMMAND_PATHS", sorted(service_command_path_set()))
        print("SERVICE_HEALTH", snapshot.health_status)
        print("SERVICE_READY", snapshot.readiness_status)
        print("SERVICE_MODE", snapshot.access_mode)
        print("LIMITS_ROLE", snapshot.limits_role)
        print("LIMITS_REMAIN", snapshot.remaining_custom_chats)
        print("LIMITS_CAN_CREATE", snapshot.can_create_custom_chats)

        if snapshot.health_status != "ok":
            raise RuntimeError("health shortcut returned unexpected status")
        if snapshot.readiness_status != "ready":
            raise RuntimeError("readiness shortcut returned unexpected status")
        if snapshot.access_mode not in {"open", "closed"}:
            raise RuntimeError("mode shortcut returned unexpected value")
        if snapshot.limits_role != "user":
            raise RuntimeError("limits role mismatch")


def _verify_command_map(route_map: dict[str, set[str]]) -> None:
    for command in M5CARDPUTER_CONSOLE_SERVICE_COMMANDS:
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
        "/admin/mode/set",
    }
    overlap = sorted(forbidden_paths & service_command_path_set())
    if overlap:
        raise RuntimeError(f"service shortcuts must stay safe/read-only: {overlap}")


if __name__ == "__main__":
    main()
