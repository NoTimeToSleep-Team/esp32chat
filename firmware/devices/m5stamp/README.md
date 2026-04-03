# M5Stamp S3 Nodes

Internal helper firmware target for M5Stamp S3 devices.

Implemented as MVP in `v0.08.02`.

Native Arduino runtime is available in `m5stamp_s3.ino`.
Preset defaults live in `../../arduino/presets/m5stamp_s3_preset.h`.

## Scope

- heartbeat envelope generation with status transitions (`ok`/`degraded`/`hold_state`);
- indicator state mapping for service-node diagnostics;
- telemetry hooks registry for lightweight sensor integration;
- emergency signal registry with severity escalation;
- read-only server health/readiness gateway (no server-control commands).

## Files

- `config.py` - node configuration.
- `models.py` - statuses, indicator model, telemetry snapshot model.
- `signals.py` - emergency signal catalog and status derivation.
- `indicator.py` - indicator state machine.
- `telemetry_hooks.py` - pluggable telemetry hooks.
- `heartbeat.py` - protocol envelope factory for register/heartbeat/telemetry.
- `command_map.py` - explicit allowed read-only server commands.
- `server_api.py` - read-only health gateway.
- `controller.py` - node-level orchestration API.
- `verify_mvp.py` - end-to-end local verification against `TestClient`.

## Verification

Run from project root:

```bash
python -m firmware.devices.m5stamp.verify_mvp
```

Python modules in this directory remain as host-side simulation and verification harnesses.
Profile metadata lists harness files under `host_harness_entries`.
