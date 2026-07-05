# Device Registration Integration

This document tracks software-level e2e integration for device registration and telemetry.

## Scope (`v0.15.01`)

- register device node in server runtime registry;
- submit heartbeat status;
- submit telemetry snapshot;
- read last known device status from server.

Current reference flow uses `esp32_service` as the first integrated device type.

## Server API Endpoints

- `POST /ops/api/devices/register`
- `POST /ops/api/devices/heartbeat`
- `POST /ops/api/devices/telemetry`
- `GET /ops/api/devices/{device_id}/status`

All endpoints require admin `session_token` and operate on `device_registry` state.

## Local Verification

Run from project root:

```bash
python -m firmware.devices.esp32_service.verify_registration_e2e
```

Verification asserts:

- protocol envelope types (`device.register.request`, `device.heartbeat`, `telemetry.snapshot`);
- successful API writes for register/heartbeat/telemetry;
- status endpoint reflects latest integrated metadata (`registration`, `last_heartbeat`, `last_telemetry`).

## Hardware Note

This check is software e2e against FastAPI `TestClient`.
Real hardware/network behavior remains a separate validation step.
