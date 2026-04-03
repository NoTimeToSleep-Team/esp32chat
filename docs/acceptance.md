# Acceptance Checklist

This checklist defines minimum acceptance criteria for RC gating.

Stage reference: `v0.16.01`.

## Acceptance Rules

- Only executed checks can be marked as verified.
- Software checks and hardware checks are tracked separately.
- Hardware-dependent behavior remains pending until validated on real devices.

## Core Server Acceptance

- `AC-SRV-01` auth and session lifecycle works for admin/user/device clients; guest remains web-only.
- `AC-SRV-02` rate limiting and brute-force guard return defensive blocking behavior.
- `AC-SRV-03` chat/blog/support/admin APIs enforce role boundaries and predictable errors.
- `AC-SRV-04` ops-safe behavior (degraded mode, safe shutdown flow, backup/incidents) remains reachable through APIs.

## Firmware Acceptance

- `AC-FW-01` shared protocol samples validate against `contracts/messages/*.json`.
- `AC-FW-02` shared transport queue validates retry, dedup, reconnect sync behavior.
- `AC-FW-03` each implemented device profile has at least one runnable local verifier.
- `AC-FW-04` device profiles keep realistic limits (no fake media/offline/server claims).

## Integration Acceptance (Stage 15)

- `AC-INT-01` device registration e2e: register -> heartbeat -> telemetry -> status.
- `AC-INT-02` chat e2e parity: one message event is consistent between web realtime and device protocol mapping.
- `AC-INT-03` blog/support/admin e2e flow: admin publish/reply/update is visible in user/device read flow.
- `AC-INT-04` autonomy matrix and autonomy profiles are present and consistent with device profile keys.

## Documentation Acceptance

- `AC-DOC-01` integration docs exist: `docs/integration-device.md`, `docs/integration-chat.md`, `docs/integration-ops.md`.
- `AC-DOC-02` autonomy doc exists: `docs/autonomy-matrix.md` and profile definitions in `firmware/profiles/autonomy/`.
- `AC-DOC-03` verification plan exists with command order and expected artifacts.

## Hardware-Pending Acceptance

- `AC-HW-01` real device network reliability and reconnect behavior.
- `AC-HW-02` power/thermal envelope under continuous operation.
- `AC-HW-03` real operator workflow on M5Tab and handheld clients.
- `AC-HW-04` real safe-shutdown sequence with peripheral state integrity.

These hardware items are mandatory for final field-ready acceptance but are out of software-only verification scope.

Tracking artifacts:

- `docs/hardware-validation-checklist.md`
- `docs/hardware-validation-log-template.md`
- `docs/hardware-validation-log-bootstrap.md`
- `docs/field-ready-gate.md`
