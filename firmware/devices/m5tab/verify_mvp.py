from __future__ import annotations

import os
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Mapping

from .command_map import M5TAB_TELEMETRY_COMMANDS, command_path_set
from .config import M5TabConfig
from .controller import M5TabController
from .server_api import CommandSender, GatewayError, TelemetryGateway


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
            raise GatewayError(code="unsupported_method", message=f"Unsupported method: {method}")

        if response.status_code >= 400:
            raise GatewayError(
                code="http_error",
                message=f"HTTP {response.status_code} for {method} {path}: {response.text}",
                status_code=response.status_code,
            )

        payload = response.json()
        if not isinstance(payload, dict):
            raise GatewayError(code="invalid_json", message="Response must be JSON object")
        return payload


def main() -> None:
    project_root = Path(__file__).resolve().parents[3]
    server_root = project_root / "server"

    db_name = f"local_chat_m5tab_shell_test_{uuid.uuid4().hex}.db"
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
            ("m5tab-admin", hash_password("m5tab-secret-123"), now_ms, now_ms),
        )
        conn.commit()
        conn.close()

        login = client.post(
            "/auth/login",
            json={"login": "m5tab-admin", "password": "m5tab-secret-123", "client_kind": "web"},
        )
        if login.status_code != 200:
            raise RuntimeError(f"m5tab admin login failed: {login.status_code} {login.text}")
        token = login.json()["session"]["token"]

        mode_update = client.post(
            "/mode",
            headers={"X-Session-Token": token},
            json={"access_mode": "closed"},
        )
        if mode_update.status_code != 200:
            raise RuntimeError(f"mode update failed: {mode_update.status_code} {mode_update.text}")

        degraded_update = client.post(
            "/ops/api/degraded-mode",
            json={
                "session_token": token,
                "enabled": True,
                "reason": "m5tab info screen validation",
            },
        )
        if degraded_update.status_code != 200:
            raise RuntimeError(
                f"degraded mode update failed: {degraded_update.status_code} {degraded_update.text}"
            )

        incident_create = client.post(
            "/ops/api/incidents",
            json={
                "session_token": token,
                "level": "warning",
                "title": "m5tab info test incident",
                "source": "m5tab",
                "details": {"note": "info screen count validation"},
            },
        )
        if incident_create.status_code != 200:
            raise RuntimeError(
                f"incident create failed: {incident_create.status_code} {incident_create.text}"
            )

        sender = TestClientCommandSender(client)
        gateway = TelemetryGateway(sender)
        controller = M5TabController(config=M5TabConfig(), gateway=gateway)

        shell_state = controller.start_shell(now_ms=4001)
        info = controller.refresh_info(now_ms=4002, session_token=token)
        bundle = gateway.telemetry_bundle(session_token=token)

        expected_health = _mapping(bundle.get("health"))
        expected_readiness = _mapping(bundle.get("readiness"))
        expected_mode = _mapping(bundle.get("mode"))
        expected_runtime = _mapping(bundle.get("runtime"))
        expected_incidents = _mapping(bundle.get("incidents"))

        expected_runtime_payload = _mapping(expected_runtime.get("runtime"))
        expected_readiness_checks = _mapping(expected_readiness.get("checks"))
        expected_data_layer = _mapping(expected_readiness.get("data_layer"))

        print("COMMAND_MAP_COUNT", len(M5TAB_TELEMETRY_COMMANDS))
        print("COMMAND_PATHS", sorted(command_path_set()))
        print("SHELL_CONNECTED", shell_state.connected, shell_state.connection_state.value)
        print("INFO_HEALTH", info.health_status)
        print("INFO_READY", info.readiness_status)
        print("INFO_PROFILE", info.profile)
        print("INFO_MODE", info.access_mode)
        print("INFO_DEGRADED", info.runtime_degraded_mode)
        print("INFO_INCIDENTS", info.active_incidents_count)
        print("INFO_MIGRATIONS", info.applied_migrations)

        if info.health_status != str(expected_health.get("status")):
            raise RuntimeError("info.health_status mismatch")
        if info.readiness_status != str(expected_readiness.get("status")):
            raise RuntimeError("info.readiness_status mismatch")
        if info.profile != str(expected_health.get("profile")):
            raise RuntimeError("info.profile mismatch")
        if info.access_mode != str(expected_mode.get("access_mode")):
            raise RuntimeError("info.access_mode mismatch")
        if info.runtime_degraded_mode is not bool(expected_runtime_payload.get("degraded_mode")):
            raise RuntimeError("info.runtime_degraded_mode mismatch")
        if info.data_layer_initialized is not bool(expected_readiness_checks.get("data_layer_initialized")):
            raise RuntimeError("info.data_layer_initialized mismatch")
        if info.applied_migrations != _to_int(expected_data_layer.get("applied_migrations"), default=0):
            raise RuntimeError("info.applied_migrations mismatch")
        if info.active_incidents_count != _to_int(expected_incidents.get("count"), default=0):
            raise RuntimeError("info.active_incidents_count mismatch")
        if not shell_state.connected:
            raise RuntimeError("shell must be connected after successful health check")


def _verify_command_map(route_map: dict[str, set[str]]) -> None:
    for command in M5TAB_TELEMETRY_COMMANDS:
        methods = route_map.get(command.path)
        if methods is None:
            raise RuntimeError(f"missing server route for command: {command.path}")
        if command.method.upper() not in methods:
            raise RuntimeError(
                f"method mismatch for route {command.path}: expected {command.method}, actual {sorted(methods)}"
            )

    forbidden_paths = {
        "/ops/api/degraded-mode",
        "/ops/api/shutdown/dry-run",
        "/ops/api/backups",
        "/ops/api/backups/dry-run",
        "/ops/api/backups/restore/dry-run",
    }
    overlap = sorted(forbidden_paths & command_path_set())
    if overlap:
        raise RuntimeError(f"m5tab info command map must stay telemetry-only: {overlap}")


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _to_int(value: Any, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return default


if __name__ == "__main__":
    main()
