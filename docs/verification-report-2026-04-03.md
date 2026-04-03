# Verification Report (2026-04-03)

This report captures the executed software verification sweep based on `docs/verification-plan.md`.

## Result

- Overall status: `pass` (software checks executed in current environment).
- Scope: steps 1-4 from verification plan.
- Hardware queue (step 5) remains pending by design.
- One-command automation sweep executed and passed.

## Executed Commands

### Step 1 - Contracts and Shared Runtime

```bash
python -m firmware.common.protocol.verify_contract_samples
python -m firmware.common.transport.verify_transport_queue
```

Observed:

- `CONTRACT_SAMPLES_VALIDATED 15`
- `CONTRACT_SAMPLES_ROUNDTRIP 15`
- queue retry/dedup/reconnect flow reported expected counters with no rejection errors.

### Step 2 - Device-Level Software Verifiers

```bash
python -m firmware.devices.esp32_service.verify_mvp
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

Observed:

- all listed verifiers completed successfully;
- command-map checks in verifiers remained consistent with current server API routes;
- no guest-mode leakage was reported for hardware client flows.

### Step 3 - Stage 15 Integration Verifiers

```bash
python -m firmware.devices.esp32_service.verify_registration_e2e
python -m firmware.integration.verify_chat_e2e
python -m firmware.integration.verify_ops_e2e
```

Observed:

- registration/heartbeat/telemetry/status integration passed;
- chat parity verifier reported `PROTOCOL_MESSAGE_TYPE chat.message.event` and matching parity text;
- ops e2e verifier reported final support status `resolved` with blog + support flow assertions satisfied.

### Step 4 - Profile, Autonomy, and Native Runtime Consistency

```bash
python -c "import json, pathlib; [json.loads(p.read_text(encoding='utf-8')) for p in pathlib.Path('firmware/profiles').glob('*.json')]; print('profiles_ok')"
python firmware/profiles/autonomy/verify_profiles.py
python firmware/arduino/verify_native_layout.py
```

Observed:

- `profiles_ok`
- `DEVICE_PROFILE_COUNT 10`
- `AUTONOMY_PROFILE_COUNT 7`
- `NATIVE_LAYOUT_PROFILE_COUNT 10`
- `NATIVE_LAYOUT_HARNESS_COUNT 21`

### Additional Sweep - One-Command Runner

```bash
python docs/tools/run_software_verification_sweep.py --with-compileall
```

Observed:

- `SWEEP_GROUPS_SELECTED ['contracts', 'devices', 'integration', 'native', 'profiles']`
- `SWEEP_COMMAND_COUNT 27`
- `SWEEP_STATUS PASS`
- compile step in sweep completed successfully.

### Additional Sweep - Full Python Compile

```bash
python -m compileall server/app firmware
```

Observed:

- compile walk completed for `server/app` and `firmware` without syntax errors.

### Additional Sweep - Targeted Group Run

```bash
python docs/tools/run_software_verification_sweep.py --group profiles --group native
```

Observed:

- `SWEEP_GROUPS_SELECTED ['native', 'profiles']`
- `SWEEP_COMMAND_COUNT 3`
- `SWEEP_STATUS PASS`

## Not Executed in This Report

Hardware validation queue (verification plan step 5):

- real network reconnect/latency checks on physical topology;
- long-run power and thermal checks;
- real operator drills on M5Tab and handheld hardware;
- physical safe-shutdown path validation.

These remain required for field-ready signoff.

Execution artifacts prepared:

- `docs/hardware-validation-checklist.md`
- `docs/hardware-validation-log-template.md`
- `docs/hardware-validation-log-bootstrap.md`
- `docs/field-ready-gate.md`

Helper sanity check executed:

```bash
python docs/tools/evaluate_hardware_log.py docs/hardware-validation-log-bootstrap.md
```

Observed: `HW_GATE_DECISION PENDING` (expected before physical run evidence).

Additional helper runs:

```bash
python docs/tools/new_hardware_log.py --build-tag RC1
python docs/tools/evaluate_hardware_log.py docs/hardware-validation-log-2026-04-03-session-02.md
python docs/tools/evaluate_field_ready_gate.py --log docs/hardware-validation-log-2026-04-03-session-02.md
python docs/tools/evaluate_all_hardware_logs.py
```

Observed:

- generated log: `docs/hardware-validation-log-2026-04-03-session-02.md`;
- hardware log helper decision: `PENDING`;
- field-ready gate helper decision: `PENDING`.
- all-logs helper latest decision: `PENDING`.
