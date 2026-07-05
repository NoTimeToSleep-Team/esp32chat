# Hardware Validation Checklist

This checklist defines the minimum physical-device validation package required for field-ready signoff.

Status: `pending` (software baseline only at RC1).

## 1. Test Environment Baseline

- `HW-ENV-01` Raspberry Pi 5 is the only main server in the test stand.
- `HW-ENV-02` device inventory and firmware profile IDs are recorded before runs.
- `HW-ENV-03` Wi-Fi topology and power conditions are documented.
- `HW-ENV-04` log capture path is defined for server and device-side evidence.

## 2. Reconnect and Network Reliability (`AC-HW-01`)

- `HW-NET-01` short disconnect/reconnect for each connected device profile.
- `HW-NET-02` repeated reconnect cycle (at least 10 iterations) for chat-capable clients.
- `HW-NET-03` message continuity check after reconnect for text-first clients.
- `HW-NET-04` heartbeat recovery check for internal service devices.

Pass criteria:

- no unrecoverable session lockout in normal reconnect cycle;
- chat/blog/support flows recover without inconsistent user state;
- internal service heartbeat resumes without manual DB intervention.

## 3. Power and Thermal Envelope (`AC-HW-02`)

- `HW-PWR-01` sustained runtime (minimum 4h) under normal telemetry/chat load.
- `HW-PWR-02` sustained runtime under peak synthetic interaction window.
- `HW-PWR-03` thermal and throttling observation capture for each active device category.
- `HW-PWR-04` controlled reboot and recovery after sustained run.

Pass criteria:

- no thermal shutdown or repeated crash loops;
- no persistent degraded state after controlled reboot;
- no data corruption symptoms in core server flows.

## 4. Operator Workflow on Real Devices (`AC-HW-03`)

- `HW-OPS-01` M5Tab admin flow on hardware (users/support/blog/rfid/mode).
- `HW-OPS-02` handheld chat/blog/support read/write flow on at least one device per family.
- `HW-OPS-03` role boundaries checked from physical clients (user vs admin).
- `HW-OPS-04` incident creation and operator response workflow drill.

Pass criteria:

- operator can complete documented actions without hidden/manual bypass;
- role boundaries match API contracts;
- incident flow leaves auditable evidence.

## 5. Safe Shutdown on Physical Topology (`AC-HW-04`)

- `HW-SAFE-01` graceful shutdown sequence initiated from operator flow.
- `HW-SAFE-02` write-flush verification before power cut.
- `HW-SAFE-03` reboot and state integrity check after shutdown.
- `HW-SAFE-04` emergency-path drill when graceful shutdown is interrupted.

Pass criteria:

- shutdown sequence completes with no critical data-loss symptom;
- restart returns to valid service state;
- incident log captures interrupted sequence details.

## 6. Evidence Package

For each scenario, keep:

- timestamp and operator ID;
- devices involved (`profile_id`, hardware serial if available);
- observed result (`pass`/`fail`/`blocked`);
- short evidence pointer (log snippet/screenshot/path).

Use `docs/hardware-validation-log-template.md` for run recording.
