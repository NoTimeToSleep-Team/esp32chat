from __future__ import annotations

import os
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Mapping

from firmware.common.protocol.constants import MessageType

from .config import Esp32ServiceConfig
from .controller import Esp32ServiceController
from .integration_command_map import ESP32_INTEGRATION_COMMANDS, command_path_set
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

    db_name = f"local_chat_device_registration_e2e_{uuid.uuid4().hex}.db"
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
        connection = sqlite3.connect(str(db_path))
        connection.execute(
            """
            INSERT INTO users(login, password_hash, role, status, created_at_ms, updated_at_ms, phone, registration_device_id)
            VALUES (?, ?, 'admin', 'active', ?, ?, NULL, NULL)
            """,
            ("integration-admin", hash_password("integration-secret-123"), now_ms, now_ms),
        )
        connection.commit()
        connection.close()

        login = client.post(
            "/auth/login",
            json={"login": "integration-admin", "password": "integration-secret-123", "client_kind": "web"},
        )
        if login.status_code != 200:
            raise RuntimeError(f"admin login failed: {login.status_code} {login.text}")
        token = login.json()["session"]["token"]

        sender = TestClientCommandSender(client)
        gateway = ServerOpsGateway(sender)
        config = Esp32ServiceConfig(ops_session_token=token, boot_id="boot-v0-15-01")
        controller = Esp32ServiceController(config=config, gateway=gateway)

        controller.feed_watchdog(now_ms=11000)
        register_envelope = controller.register_boot(now_ms=11001)
        heartbeat_envelope = controller.heartbeat(now_ms=11002, uptime_ms=33000, network_ok=True)
        telemetry_envelope = controller.telemetry_snapshot(
            now_ms=11003,
            snapshot=TelemetrySnapshot(
                power=PowerSample(vin_mv=5021, current_ma=405),
                temperature=ThermalSample(board_c=43.2, ambient_c=30.0),
                service_flags=ServiceFlags(
                    watchdog_ok=True,
                    safe_shutdown_ready=True,
                    network_ok=True,
                ),
            ),
        )

        register_payload = gateway.register_device(
            session_token=token,
            device_id=config.device_uid,
            device_type=str(register_envelope.payload.get("device_type", "esp32_s3_service")),
            boot_id=str(register_envelope.payload.get("boot_id", config.boot_id)),
            transport="wifi",
            metadata={
                "firmware_version": str(register_envelope.payload.get("firmware_version", config.firmware_version)),
                "register_message_id": register_envelope.message_id,
                "register_idempotency_key": register_envelope.idempotency_key,
            },
        )

        heartbeat_payload = gateway.send_heartbeat(
            session_token=token,
            device_id=config.device_uid,
            device_type=str(register_envelope.payload.get("device_type", "esp32_s3_service")),
            heartbeat_status=str(heartbeat_envelope.payload.get("status", "ok")),
            uptime_ms=int(heartbeat_envelope.payload.get("uptime_ms", 0)),
            queue_depth=int(heartbeat_envelope.payload.get("queue_depth", 0)),
            metrics=_payload_mapping(heartbeat_envelope.payload.get("metrics")),
        )

        telemetry_payload = gateway.send_telemetry(
            session_token=token,
            device_id=config.device_uid,
            device_type=str(register_envelope.payload.get("device_type", "esp32_s3_service")),
            snapshot=telemetry_envelope.payload,
            source_message_id=telemetry_envelope.message_id,
        )

        status_payload = gateway.device_status(session_token=token, device_id=config.device_uid)

        register_device = _payload_mapping(register_payload.get("device"))
        heartbeat_device = _payload_mapping(heartbeat_payload.get("device"))
        telemetry_device = _payload_mapping(telemetry_payload.get("device"))
        status_device = _payload_mapping(status_payload.get("device"))
        status_metadata = _payload_mapping(status_device.get("metadata"))

        print("INTEGRATION_COMMAND_MAP_COUNT", len(ESP32_INTEGRATION_COMMANDS))
        print("INTEGRATION_COMMAND_PATHS", sorted(command_path_set()))
        print("REGISTER_TYPE", register_envelope.message_type)
        print("HEARTBEAT_TYPE", heartbeat_envelope.message_type)
        print("TELEMETRY_TYPE", telemetry_envelope.message_type)
        print("REGISTER_STATUS", register_payload.get("status"), register_device.get("status"))
        print("HEARTBEAT_STATUS", heartbeat_payload.get("status"), heartbeat_device.get("status"))
        print("TELEMETRY_STATUS", telemetry_payload.get("status"), telemetry_device.get("status"))
        print("STATUS_STATUS", status_payload.get("status"), status_device.get("status"))
        print("STATUS_DEVICE_ID", status_device.get("device_id"))
        print("STATUS_DEVICE_TYPE", status_device.get("device_type"))
        print("HAS_REGISTRATION", "registration" in status_metadata)
        print("HAS_HEARTBEAT", "last_heartbeat" in status_metadata)
        print("HAS_TELEMETRY", "last_telemetry" in status_metadata)

        if register_envelope.message_type != MessageType.DEVICE_REGISTER_REQUEST.value:
            raise RuntimeError("register envelope message_type mismatch")
        if heartbeat_envelope.message_type != MessageType.DEVICE_HEARTBEAT.value:
            raise RuntimeError("heartbeat envelope message_type mismatch")
        if telemetry_envelope.message_type != MessageType.TELEMETRY_SNAPSHOT.value:
            raise RuntimeError("telemetry envelope message_type mismatch")

        if register_payload.get("status") != "ok":
            raise RuntimeError("device register API failed")
        if register_device.get("status") != "registered":
            raise RuntimeError("register status mismatch")

        if heartbeat_payload.get("status") != "ok":
            raise RuntimeError("heartbeat API failed")
        heartbeat_status = str(heartbeat_device.get("status", ""))
        if not heartbeat_status.startswith("heartbeat_"):
            raise RuntimeError(f"heartbeat status mismatch: {heartbeat_status}")

        if telemetry_payload.get("status") != "ok":
            raise RuntimeError("telemetry API failed")
        if telemetry_device.get("status") != "telemetry":
            raise RuntimeError("telemetry status mismatch")

        if status_payload.get("status") != "ok":
            raise RuntimeError("status API failed")
        if status_device.get("device_id") != config.device_uid:
            raise RuntimeError("status device_id mismatch")
        if status_device.get("device_type") != register_envelope.payload.get("device_type"):
            raise RuntimeError("status device_type mismatch")
        if "registration" not in status_metadata:
            raise RuntimeError("status metadata missing registration payload")
        if "last_heartbeat" not in status_metadata:
            raise RuntimeError("status metadata missing heartbeat payload")
        if "last_telemetry" not in status_metadata:
            raise RuntimeError("status metadata missing telemetry payload")


def _verify_command_map(route_map: dict[str, set[str]]) -> None:
    for command in ESP32_INTEGRATION_COMMANDS:
        methods = route_map.get(command.path_template)
        if methods is None:
            raise RuntimeError(f"missing server route for integration command: {command.path_template}")
        if command.method.upper() not in methods:
            raise RuntimeError(
                f"method mismatch for route {command.path_template}: expected {command.method}, actual {sorted(methods)}"
            )


def _payload_mapping(value: object) -> dict[str, object]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


if __name__ == "__main__":
    main()
