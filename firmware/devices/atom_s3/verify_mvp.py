from __future__ import annotations

import os
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Mapping

from .command_map import ATOM_ALLOWED_COMMANDS, command_path_set
from .config import AtomS3Config
from .controller import AtomS3Controller
from .models import AlertSeverity, QuickAction, StatusPattern, SystemStatus
from .server_api import CommandSender, GatewayError, OpsGateway


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

    db_name = f"local_chat_atom_service_test_{uuid.uuid4().hex}.db"
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
            ("atom-admin", hash_password("atom-secret-123"), now_ms, now_ms),
        )
        conn.commit()
        conn.close()

        login = client.post(
            "/auth/login",
            json={"login": "atom-admin", "password": "atom-secret-123", "client_kind": "web"},
        )
        if login.status_code != 200:
            raise RuntimeError(f"atom admin login failed: {login.status_code} {login.text}")
        token = login.json()["session"]["token"]

        sender = TestClientCommandSender(client)
        gateway = OpsGateway(sender)
        controller = AtomS3Controller(config=AtomS3Config(ops_session_token=token), gateway=gateway)

        panel_initial = controller.status_panel(now_ms=3001)
        maintenance_on = controller.execute_quick_action(
            action=QuickAction.MAINTENANCE_MODE_ON,
            reason="atom maintenance mode",
            now_ms=3002,
        )
        warning_incident = controller.raise_alert(
            alert_id="network_degraded",
            severity=AlertSeverity.WARNING,
            message="network jitter detected",
            now_ms=3003,
        )
        critical_incident = controller.raise_alert(
            alert_id="watchdog_timeout",
            severity=AlertSeverity.CRITICAL,
            message="watchdog timeout escalated",
            now_ms=3004,
        )
        panel_critical = controller.status_panel(now_ms=3005)

        shutdown = controller.execute_quick_action(
            action=QuickAction.SAFE_SHUTDOWN_DRY_RUN,
            reason="atom emergency dry-run",
            now_ms=3006,
        )
        network_reset = controller.execute_quick_action(
            action=QuickAction.SIGNAL_NETWORK_RESET,
            reason="operator requested network reset",
            now_ms=3007,
        )
        incidents = controller.list_incidents(limit=20)

        controller.clear_alert(alert_id="watchdog_timeout")
        controller.clear_alert(alert_id="network_degraded")
        controller.clear_alert(alert_id="network_reset_requested")
        maintenance_off = controller.execute_quick_action(
            action=QuickAction.MAINTENANCE_MODE_OFF,
            reason="atom maintenance complete",
            now_ms=3008,
        )
        panel_final = controller.status_panel(now_ms=3009)
        readiness = controller.readiness()

        print("COMMAND_MAP_COUNT", len(ATOM_ALLOWED_COMMANDS))
        print("COMMAND_PATHS", sorted(command_path_set()))
        print("INITIAL_STATUS", panel_initial.system_status.value, panel_initial.pattern.value)
        print("MAINTENANCE_ON", maintenance_on.get("status"), maintenance_on.get("runtime", {}).get("degraded_mode"))
        print("WARNING_INCIDENT", warning_incident.get("status"), warning_incident.get("incident", {}).get("status"))
        print("CRITICAL_INCIDENT", critical_incident.get("status"), critical_incident.get("incident", {}).get("status"))
        print("CRITICAL_PANEL", panel_critical.system_status.value, panel_critical.pattern.value)
        print("SHUTDOWN", shutdown.get("status"), shutdown.get("run", {}).get("status"))
        print("NETWORK_RESET", network_reset.get("status"), network_reset.get("incident", {}).get("status"))
        print("INCIDENTS_COUNT", incidents.get("count"))
        print("MAINTENANCE_OFF", maintenance_off.get("status"), maintenance_off.get("runtime", {}).get("degraded_mode"))
        print("FINAL_STATUS", panel_final.system_status.value, panel_final.pattern.value)
        print("READINESS_STATUS", readiness.get("status"))

        if panel_initial.system_status != SystemStatus.OK:
            raise RuntimeError("expected initial system status to be ok")
        if maintenance_on.get("runtime", {}).get("degraded_mode") is not True:
            raise RuntimeError("maintenance mode on action failed")
        if panel_critical.system_status != SystemStatus.HOLD_STATE:
            raise RuntimeError("critical alert should drive hold_state")
        if panel_critical.pattern != StatusPattern.BLINK_RED_FAST:
            raise RuntimeError("critical alert should drive red fast blink")
        if shutdown.get("run", {}).get("status") != "completed":
            raise RuntimeError("shutdown dry-run action failed")
        if not isinstance(incidents.get("count"), int) or incidents.get("count") < 3:
            raise RuntimeError("expected incidents to include warning/critical/network reset")
        if maintenance_off.get("runtime", {}).get("degraded_mode") is not False:
            raise RuntimeError("maintenance mode off action failed")
        if panel_final.system_status != SystemStatus.OK:
            raise RuntimeError("expected final system status to be ok")
        if readiness.get("status") != "ready":
            raise RuntimeError("readiness check mismatch")


def _verify_command_map(route_map: dict[str, set[str]]) -> None:
    for command in ATOM_ALLOWED_COMMANDS:
        methods = route_map.get(command.path)
        if methods is None:
            raise RuntimeError(f"missing server route for command: {command.path}")
        if command.method.upper() not in methods:
            raise RuntimeError(
                f"method mismatch for route {command.path}: expected {command.method}, actual {sorted(methods)}"
            )

    forbidden_paths = {
        "/ops/api/backups",
        "/ops/api/backups/dry-run",
        "/ops/api/backups/restore/dry-run",
    }
    overlap = sorted(forbidden_paths & command_path_set())
    if overlap:
        raise RuntimeError(f"atom command map must not expose backup operations: {overlap}")


if __name__ == "__main__":
    main()
