from __future__ import annotations

import os
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Mapping

from .command_map import FLIPPER_ZERO_COMMANDS, command_path_set
from .config import FlipperZeroConfig
from .controller import FlipperZeroController
from .models import ConnectionState, FlipperScreen
from .server_api import CommandSender, FlipperAuthGateway
from .shell import StaticCapabilityDetector


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
    project_root = Path(__file__).resolve().parents[3]
    server_root = project_root / "server"

    db_name = f"local_chat_flipper_shell_test_{uuid.uuid4().hex}.db"
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
                "flipper-user",
                hash_password("flipper-secret-123"),
                now_ms,
                now_ms,
            ),
        )
        conn.commit()
        conn.close()

        sender = RecordingTestClientSender(client)
        gateway = FlipperAuthGateway(sender)
        config = FlipperZeroConfig(client_kind="device")

        limited_controller = FlipperZeroController(
            config=config,
            gateway=gateway,
            capability_detector=StaticCapabilityDetector(wifi_dev_board_attached=False),
        )
        limited_detected = limited_controller.detect_capabilities(now_ms=9601)
        limited_connected = limited_controller.start_shell(now_ms=9602)
        limited_login_error: str | None = None
        try:
            limited_controller.secure_login(
                login="flipper-user",
                password="flipper-secret-123",
                now_ms=9603,
            )
        except RuntimeError as exc:
            limited_login_error = str(exc)

        network_controller = FlipperZeroController(
            config=config,
            gateway=gateway,
            capability_detector=StaticCapabilityDetector(wifi_dev_board_attached=True),
        )
        network_detected = network_controller.detect_capabilities(now_ms=9611)
        connected = network_controller.start_shell(now_ms=9612)
        logged_in = network_controller.secure_login(
            login="flipper-user",
            password="flipper-secret-123",
            now_ms=9613,
        )
        if logged_in.session is None:
            raise RuntimeError("secure_login did not create session")
        opened_chat = network_controller.open_screen(screen=FlipperScreen.CHAT, now_ms=9614)
        opened_blog = network_controller.open_screen(screen=FlipperScreen.BLOG, now_ms=9615)
        resumed = network_controller.resume_session(session_token=logged_in.session.token, now_ms=9616)
        mode_payload = gateway.mode()
        logged_out = network_controller.logout(now_ms=9617)

        login_kind = _extract_call_value(sender.calls, path="/auth/login", field="client_kind", source="json_payload")
        session_kind = _extract_session_kind(sender.calls)
        has_health_call = _has_call(sender.calls, path="/health", method="GET")

        print("COMMAND_MAP_COUNT", len(FLIPPER_ZERO_COMMANDS))
        print("COMMAND_PATHS", sorted(command_path_set()))
        print("LIMITED_MODE", limited_detected.connection_state.value, limited_detected.capability.mode)
        print("LIMITED_CONNECT", limited_connected.connection_state.value, limited_connected.connected)
        print("LIMITED_LOGIN_ERROR", limited_login_error)
        print("NETWORK_MODE", network_detected.connection_state.value, network_detected.capability.mode)
        print("SHELL_CONNECTED", connected.connected, connected.connection_state.value)
        print("LOGIN_STATE", logged_in.connection_state.value, logged_in.session.login)
        print("CHAT_SCREEN", opened_chat.active_screen.value)
        print("BLOG_SCREEN", opened_blog.active_screen.value)
        print("RESUME_STATE", resumed.connection_state.value, resumed.session is not None)
        print("MODE_ACCESS", mode_payload.get("access_mode"))
        print("LOGOUT_STATE", logged_out.connection_state.value, logged_out.session is None)
        print("LOGIN_CLIENT_KIND", login_kind)
        print("SESSION_CLIENT_KIND", session_kind)
        print("HAS_HEALTH_CALL", has_health_call)

        if limited_detected.connection_state != ConnectionState.LIMITED:
            raise RuntimeError("limited capability detection did not switch to limited mode")
        if limited_connected.connection_state != ConnectionState.LIMITED:
            raise RuntimeError("start_shell must keep limited mode without wifi dev board")
        if limited_login_error is None or "limited mode" not in limited_login_error:
            raise RuntimeError("secure_login must fail in limited mode")
        if network_detected.connection_state != ConnectionState.DISCONNECTED:
            raise RuntimeError("network capability detection did not keep disconnected pre-connect state")
        if connected.connection_state != ConnectionState.CONNECTED:
            raise RuntimeError("shell did not enter connected state")
        if logged_in.connection_state != ConnectionState.AUTHENTICATED:
            raise RuntimeError("secure_login did not authenticate")
        if opened_chat.active_screen != FlipperScreen.CHAT:
            raise RuntimeError("chat navigation failed")
        if opened_blog.active_screen != FlipperScreen.BLOG:
            raise RuntimeError("blog navigation failed")
        if resumed.session is None:
            raise RuntimeError("resume_session did not restore session")
        if mode_payload.get("status") != "ok":
            raise RuntimeError("mode read failed")
        if logged_out.session is not None:
            raise RuntimeError("logout did not clear session")
        if login_kind != "device":
            raise RuntimeError(f"secure_login must use device client_kind, got {login_kind}")
        if session_kind != "device":
            raise RuntimeError(f"session check must use device client_kind, got {session_kind}")
        if not has_health_call:
            raise RuntimeError("network connect must probe /health")


def _verify_command_map(route_map: dict[str, set[str]]) -> None:
    for command in FLIPPER_ZERO_COMMANDS:
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
        "/rfid/api/cards",
    }
    overlap = sorted(forbidden_paths & command_path_set())
    if overlap:
        raise RuntimeError(f"flipper command map contains forbidden paths: {overlap}")


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
