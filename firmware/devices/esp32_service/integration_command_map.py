from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IntegrationCommand:
    command_id: str
    method: str
    path_template: str
    requires_session: bool
    description: str


ESP32_INTEGRATION_COMMANDS: tuple[IntegrationCommand, ...] = (
    IntegrationCommand(
        command_id="device_register",
        method="POST",
        path_template="/ops/api/devices/register",
        requires_session=True,
        description="Register device node in server runtime registry",
    ),
    IntegrationCommand(
        command_id="device_heartbeat",
        method="POST",
        path_template="/ops/api/devices/heartbeat",
        requires_session=True,
        description="Submit heartbeat status for registered device",
    ),
    IntegrationCommand(
        command_id="device_telemetry",
        method="POST",
        path_template="/ops/api/devices/telemetry",
        requires_session=True,
        description="Submit telemetry snapshot for registered device",
    ),
    IntegrationCommand(
        command_id="device_status",
        method="GET",
        path_template="/ops/api/devices/{device_id}/status",
        requires_session=True,
        description="Read last known runtime status for device node",
    ),
)


def command_path_set() -> set[str]:
    return {item.path_template for item in ESP32_INTEGRATION_COMMANDS}
