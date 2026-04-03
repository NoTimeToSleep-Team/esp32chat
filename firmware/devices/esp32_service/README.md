# ESP32 Service Controller

Internal service firmware target for ESP32-S3 USB-OTG.

Implemented as MVP in `v0.08.01`.

`v0.15.01` adds registration/telemetry e2e verification against server device-runtime APIs.
`v0.15.02` adds cross-flow chat e2e verifier under `firmware/integration/verify_chat_e2e.py`.

Native Arduino runtime is available in `esp32_service.ino`.
Preset defaults live in `../../arduino/presets/esp32_service_preset.h`.

## Scope

- telemetry envelope generation (`device.register.request`, `device.heartbeat`, `telemetry.snapshot`);
- watchdog supervision;
- diagnostics aggregation;
- safe ops commands (`/ops/api/degraded-mode`, `/ops/api/shutdown/dry-run`).

## Files

- `config.py` - runtime configuration.
- `models.py` - telemetry/diagnostics data models.
- `watchdog.py` - watchdog supervisor.
- `diagnostics.py` - diagnostics collector.
- `command_map.py` - command-to-server API mapping.
- `server_api.py` - gateway abstraction for server HTTP commands.
- `telemetry.py` - protocol envelope factory.
- `controller.py` - service-controller orchestration API.
- `verify_mvp.py` - end-to-end local verification against FastAPI `TestClient`.
- `integration_command_map.py` - device-runtime integration endpoint mapping.
- `verify_registration_e2e.py` - device registration/heartbeat/telemetry e2e verification.

## Verification

Run from project root:

```bash
python -m firmware.devices.esp32_service.verify_mvp
python -m firmware.devices.esp32_service.verify_registration_e2e
```

Python modules in this directory remain as host-side simulation and verification harnesses.
Profile metadata lists harness files under `host_harness_entries`.
