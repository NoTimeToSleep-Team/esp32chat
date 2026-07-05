# Verification Plan

This plan defines ordered verification steps for software-level acceptance.

Stage reference: `v0.16.01`.

## Preconditions

- Run from project root: `D:\project`.
- Python environment with project dependencies installed.
- No claim is marked as verified unless command execution succeeded in current environment.

Optional one-command sweep:

```bash
python docs/tools/run_software_verification_sweep.py --with-compileall
```

Optional targeted run by group (repeat `--group` as needed):

```bash
python docs/tools/run_software_verification_sweep.py --group profiles --group native
```

## Step 1 - Contracts and Shared Runtime

Run:

```bash
python -m firmware.common.protocol.verify_contract_samples
python -m firmware.common.transport.verify_transport_queue
python -m firmware.common.transport.verify_uart_framing
python -m firmware.common.transport.verify_uart_transport_adapter
python -m firmware.common.transport.verify_uart_sync_retry
```

Expected:

- protocol samples validated + round-trip coverage;
- queue retry/dedup/reconnect flow passes;
- UART frame encode/parse/chunked-stream/CRC guard checks pass;
- UART envelope adapter ACK-required/ACK-optional exchange checks pass;
- UART-backed sync retry + sequence rollover checks pass.

## Step 2 - Device-Level Software Verifiers

Run:

```bash
python -m firmware.devices.esp32_service.verify_mvp
python -m firmware.devices.esp32_service.verify_sync_transport
python -m firmware.devices.m5stamp.verify_mvp
python -m firmware.devices.atom_s3.verify_mvp
python -m firmware.devices.m5tab.verify_mvp
python -m firmware.devices.m5tab.screens.admin_users.verify_flow
python -m firmware.devices.m5tab.screens.admin_ops.verify_flow
python -m firmware.devices.m5cardputer_console.verify_mvp
python -m firmware.devices.m5cardputer_console.chat.verify_flow
python -m firmware.devices.m5cardputer_console.blog.verify_flow
python -m firmware.devices.m5cardputer_console.service_actions.verify_flow
python -m firmware.devices.m5cardputer_client.verify_alignment
python -m firmware.devices.m5cardputer_client.ui.verify_flow
python -m firmware.devices.m5stickc_plus2.verify_mvp
python -m firmware.devices.m5stickc_plus2.ui.verify_flow
python -m firmware.devices.t_embed_cc1101.verify_mvp
python -m firmware.devices.t_embed_cc1101.ui.verify_flow
python -m firmware.devices.flipper_zero.verify_mvp
python -m firmware.devices.flipper_zero.ui.verify_flow
```

Expected:

- each profile-specific flow passes without guest-mode leakage into hardware clients;
- ESP32 queue sync path validates transport selection (`inmemory` and `uart`) with shared sync runtime;
- no fake media/storage capabilities asserted.

## Step 3 - Stage 15 Integration Verifiers

Run:

```bash
python -m firmware.devices.esp32_service.verify_registration_e2e
python -m firmware.integration.verify_chat_e2e
python -m firmware.integration.verify_ops_e2e
```

Expected:

- device runtime registration/heartbeat/telemetry/status path passes;
- chat event parity between web and device mapping passes;
- blog/support/admin integrated scenario passes.

## Step 4 - Profile, Autonomy, and Native Runtime Consistency

Run:

```bash
python -c "import json, pathlib; [json.loads(p.read_text(encoding='utf-8')) for p in pathlib.Path('firmware/profiles').glob('*.json')]; print('profiles_ok')"
python firmware/profiles/autonomy/verify_profiles.py
python firmware/arduino/verify_native_layout.py
```

Expected:

- all top-level firmware profiles parse;
- each referenced `autonomy_profile` has a matching autonomy definition.
- native runtime entries, Arduino presets, Flipper manifest linkage, and host harness mappings are valid.

## Step 5 - Hardware Validation Queue (Manual)

Pending hardware runs:

- reconnect and latency behavior on real network links;
- power + thermal checks under sustained runtime;
- operator flows on real M5Tab and handheld devices;
- safe shutdown on real power path and peripherals.

These steps are tracked as required for final field-ready release signoff.

Execution checklist: `docs/hardware-validation-checklist.md`.
Run logging template: `docs/hardware-validation-log-template.md`.
Starter session log: `docs/hardware-validation-log-bootstrap.md`.
Field decision rules: `docs/field-ready-gate.md`.
Operational sequence: `docs/hardware-runbook.md`.
Session generator: `docs/tools/new_hardware_log.py`.

Optional quick evaluator:

```bash
python docs/tools/evaluate_hardware_log.py docs/hardware-validation-log-bootstrap.md
python docs/tools/evaluate_field_ready_gate.py --log docs/hardware-validation-log-bootstrap.md
python docs/tools/evaluate_all_hardware_logs.py
```
