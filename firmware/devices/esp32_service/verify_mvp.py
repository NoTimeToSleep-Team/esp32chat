from __future__ import annotations

import os
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Mapping

from firmware.common.protocol.constants import MessageType

from .command_map import ESP32_SERVICE_COMMANDS
from .config import Esp32ServiceConfig
from .controller import Esp32ServiceController
from .models import PowerSample, ServiceFlags, TelemetrySnapshot, ThermalSample
from .server_api import CommandSender, GatewayError, ServerOpsGateway


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

    db_name = f"local_chat_esp32_service_test_{uuid.uuid4().hex}.db"
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
        route_map = {
            route.path: {method.upper() for method in getattr(route, "methods", set())}
            for route in app.routes
        }

        _verify_command_map(route_map)

        db_path = app.state.data_layer.database_path
        now_ms = int(time.time() * 1000)
        connection = sqlite3.connect(str(db_path))
        connection.execute(
            """
            INSERT INTO users(login, password_hash, role, status, created_at_ms, updated_at_ms, phone, registration_device_id)
            VALUES (?, ?, 'admin', 'active', ?, ?, NULL, NULL)
            """,
            ("esp32-admin", hash_password("esp32-secret-123"), now_ms, now_ms),
        )
        connection.commit()
        connection.close()

        login = client.post(
            "/auth/login",
            json={"login": "esp32-admin", "password": "esp32-secret-123", "client_kind": "web"},
        )
        if login.status_code != 200:
            raise RuntimeError(f"admin login failed: {login.status_code} {login.text}")
        token = login.json()["session"]["token"]

        sender = TestClientCommandSender(client)
        gateway = ServerOpsGateway(sender)
        config = Esp32ServiceConfig(ops_session_token=token, boot_id="boot-v0-08-01")
        controller = Esp32ServiceController(config=config, gateway=gateway)

        controller.feed_watchdog(now_ms=1000)
        register_envelope = controller.register_boot(now_ms=1001)
        heartbeat_envelope = controller.heartbeat(now_ms=1002, uptime_ms=15000, network_ok=True)
        telemetry_envelope = controller.telemetry_snapshot(
            now_ms=1003,
            snapshot=TelemetrySnapshot(
                power=PowerSample(vin_mv=5032, current_ma=412),
                temperature=ThermalSample(board_c=42.5, ambient_c=30.1),
                service_flags=ServiceFlags(
                    watchdog_ok=True,
                    safe_shutdown_ready=True,
                    network_ok=True,
                ),
            ),
        )

        health_payload = controller.server_health()
        runtime_before = controller.runtime_state()
        degraded_on = controller.set_degraded_mode(enabled=True, reason="esp32 maintenance dry-run")
        shutdown = controller.safe_shutdown_dry_run(reason="esp32 dry-run command")
        runtime_after = controller.runtime_state()
        diagnostics = controller.diagnostics_report(now_ms=1010, network_ok=True)

        print("COMMAND_MAP_COUNT", len(ESP32_SERVICE_COMMANDS))
        print("REGISTER_TYPE", register_envelope.message_type)
        print("HEARTBEAT_TYPE", heartbeat_envelope.message_type)
        print("TELEMETRY_TYPE", telemetry_envelope.message_type)
        print("HEALTH_STATUS", health_payload.get("status"))
        print("RUNTIME_BEFORE", runtime_before.get("status"), runtime_before.get("runtime", {}).get("degraded_mode"))
        print("DEGRADED_ON", degraded_on.get("status"), degraded_on.get("runtime", {}).get("degraded_mode"))
        print("SHUTDOWN_STATUS", shutdown.get("status"), shutdown.get("run", {}).get("status"))
        print("RUNTIME_AFTER", runtime_after.get("status"), runtime_after.get("runtime", {}).get("degraded_mode"))
        print("DIAGNOSTICS_WATCHDOG_OK", diagnostics.watchdog_ok)
        print("DIAGNOSTICS_QUEUE_DEPTH", diagnostics.queue_depth)

        if register_envelope.message_type != MessageType.DEVICE_REGISTER_REQUEST.value:
            raise RuntimeError("register envelope message_type mismatch")
        if heartbeat_envelope.message_type != MessageType.DEVICE_HEARTBEAT.value:
            raise RuntimeError("heartbeat envelope message_type mismatch")
        if telemetry_envelope.message_type != MessageType.TELEMETRY_SNAPSHOT.value:
            raise RuntimeError("telemetry envelope message_type mismatch")

        if health_payload.get("status") != "ok":
            raise RuntimeError("health status mismatch")
        if runtime_before.get("status") != "ok":
            raise RuntimeError("runtime_before status mismatch")
        if degraded_on.get("runtime", {}).get("degraded_mode") is not True:
            raise RuntimeError("failed to set degraded_mode=true")
        if shutdown.get("run", {}).get("status") != "completed":
            raise RuntimeError("shutdown dry run status mismatch")
        if runtime_after.get("runtime", {}).get("degraded_mode") is not True:
            raise RuntimeError("runtime_after degraded_mode mismatch")


def _verify_command_map(route_map: dict[str, set[str]]) -> None:
    for command in ESP32_SERVICE_COMMANDS:
        methods = route_map.get(command.path)
        if methods is None:
            raise RuntimeError(f"missing server route for command: {command.path}")
        if command.method.upper() not in methods:
            raise RuntimeError(
                f"method mismatch for route {command.path}: expected {command.method}, actual {sorted(methods)}"
            )


if __name__ == "__main__":
    main()
