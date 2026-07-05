from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from typing import Any, Mapping

from firmware.common.protocol.constants import MessageType

from .command_map import M5STAMP_ALLOWED_COMMANDS, command_path_set
from .config import M5StampConfig
from .controller import M5StampController
from .models import HeartbeatStatus, IndicatorPattern
from .server_api import CommandSender, GatewayError, HealthGateway
from .signals import EmergencySignal


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

    db_name = f"local_chat_m5stamp_service_test_{uuid.uuid4().hex}.db"
    os.environ["LCS_PROFILE"] = "test"
    os.environ["LCS_DATABASE_URL"] = f"sqlite:///data/sqlite/{db_name}"
    os.environ["LCS_STORAGE_ROOT"] = "data"
    os.environ["LCS_RELOAD"] = "false"

    if str(server_root) not in sys.path:
        sys.path.insert(0, str(server_root))

    from fastapi.testclient import TestClient  # type: ignore
    from app.config import get_settings  # type: ignore
    from app.main import create_app  # type: ignore

    get_settings(refresh=True)
    app = create_app()

    with TestClient(app) as client:
        route_map = {
            route.path: {method.upper() for method in getattr(route, "methods", set())}
            for route in app.routes
        }
        _verify_allowed_command_map(route_map)

        sender = TestClientCommandSender(client)
        gateway = HealthGateway(sender)
        controller = M5StampController(config=M5StampConfig(boot_id="boot-v0-08-02"), gateway=gateway)

        controller.register_hook(key="power.vin_mv", provider=lambda: 5012)
        controller.register_hook(key="power.current_ma", provider=lambda: 198)
        controller.register_hook(key="temperature.board_c", provider=lambda: 41.6)
        controller.register_hook(key="temperature.ambient_c", provider=lambda: 30.4)

        register_envelope = controller.register_boot(now_ms=2001)
        heartbeat_ok = controller.heartbeat(
            now_ms=2002,
            uptime_ms=12000,
            queue_depth=0,
            network_ok=True,
        )

        controller.activate_signal(
            signal_id=EmergencySignal.TEMP_WARNING,
            reason="board_c over warning threshold",
        )
        heartbeat_warning = controller.heartbeat(
            now_ms=2003,
            uptime_ms=13000,
            queue_depth=1,
            network_ok=True,
        )

        controller.activate_signal(
            signal_id=EmergencySignal.WATCHDOG_TIMEOUT,
            reason="watchdog timeout observed",
        )
        heartbeat_critical = controller.heartbeat(
            now_ms=2004,
            uptime_ms=14000,
            queue_depth=2,
            network_ok=True,
        )
        telemetry = controller.telemetry_snapshot(now_ms=2005, network_ok=True)

        health = controller.server_health()
        ready = controller.server_readiness()

        status_ok = heartbeat_ok.payload.get("status")
        status_warning = heartbeat_warning.payload.get("status")
        status_critical = heartbeat_critical.payload.get("status")
        indicator_pattern = controller.indicator_state.pattern.value

        print("COMMAND_MAP_COUNT", len(M5STAMP_ALLOWED_COMMANDS))
        print("COMMAND_PATHS", sorted(command_path_set()))
        print("REGISTER_TYPE", register_envelope.message_type)
        print("HEARTBEAT_OK", status_ok)
        print("HEARTBEAT_WARNING", status_warning)
        print("HEARTBEAT_CRITICAL", status_critical)
        print("INDICATOR_PATTERN", indicator_pattern)
        print("TELEMETRY_TYPE", telemetry.message_type)
        print("HEALTH_STATUS", health.get("status"))
        print("READY_STATUS", ready.get("status"))

        if register_envelope.message_type != MessageType.DEVICE_REGISTER_REQUEST.value:
            raise RuntimeError("register envelope message_type mismatch")
        if heartbeat_ok.message_type != MessageType.DEVICE_HEARTBEAT.value:
            raise RuntimeError("heartbeat_ok envelope type mismatch")
        if telemetry.message_type != MessageType.TELEMETRY_SNAPSHOT.value:
            raise RuntimeError("telemetry envelope type mismatch")

        if status_ok != HeartbeatStatus.OK.value:
            raise RuntimeError("expected heartbeat ok status")
        if status_warning != HeartbeatStatus.DEGRADED.value:
            raise RuntimeError("expected degraded status for warning signal")
        if status_critical != HeartbeatStatus.HOLD_STATE.value:
            raise RuntimeError("expected hold_state status for critical signal")
        if indicator_pattern != IndicatorPattern.BLINK_RED_FAST.value:
            raise RuntimeError("expected critical indicator pattern")

        if health.get("status") != "ok":
            raise RuntimeError("server health status mismatch")
        if ready.get("status") != "ready":
            raise RuntimeError("server readiness status mismatch")


def _verify_allowed_command_map(route_map: dict[str, set[str]]) -> None:
    for command in M5STAMP_ALLOWED_COMMANDS:
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
    }
    allowed_paths = command_path_set()
    overlap = sorted(forbidden_paths & allowed_paths)
    if overlap:
        raise RuntimeError(f"m5stamp command map must remain read-only, found forbidden paths: {overlap}")


if __name__ == "__main__":
    main()
