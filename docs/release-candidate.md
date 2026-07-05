# Release Candidate

RC tag: `RC1` (software baseline)

Stage reference: `v0.16.03`.

## Included Scope

- Stage `01`-`14` baseline implementation and device MVP verifiers.
- Stage `15` integration set:
  - device registration/telemetry e2e;
  - chat web+device parity e2e;
  - blog/support/admin ops e2e;
  - autonomy matrix and autonomy profile definitions.
- Stage `16` documentation set:
  - `docs/acceptance.md`;
  - `docs/verification-plan.md`;
  - `docs/verification-report-2026-04-03.md`;
  - `docs/known-limitations.md`;
  - `docs/operator-guide.md`.

## Verification Snapshot (Executed)

Executed in current workspace:

```bash
python -m py_compile server/app/realtime/events.py server/app/realtime/__init__.py server/app/api/chat.py server/app/api/realtime.py firmware/integration/__init__.py firmware/integration/chat_command_map.py firmware/integration/verify_chat_e2e.py
python -m py_compile firmware/integration/__init__.py firmware/integration/ops_command_map.py firmware/integration/verify_ops_e2e.py firmware/profiles/autonomy/verify_profiles.py
python -m firmware.integration.verify_chat_e2e
python -m firmware.integration.verify_ops_e2e
python -m firmware.common.protocol.verify_contract_samples
python firmware/profiles/autonomy/verify_profiles.py
python -c "import json, pathlib; [json.loads(p.read_text(encoding='utf-8')) for p in pathlib.Path('firmware/profiles').glob('*.json')]; print('profiles_ok')"
python -m compileall server/app firmware
```

## Open Items Before Field-Ready Signoff

- full hardware validation run across real devices;
- power/thermal/network reliability checks under realistic load;
- operator drills for incident + safe shutdown sequence in physical setup.

Execution pack for these open items:

- `docs/hardware-validation-checklist.md`
- `docs/hardware-validation-log-template.md`
- `docs/hardware-validation-log-bootstrap.md`
- `docs/hardware-validation-log-2026-04-03-session-01.md`
- `docs/hardware-validation-log-2026-04-03-session-02.md`
- `docs/field-ready-gate.md`
- `docs/field-ready-status.md`
- `docs/tools/new_hardware_log.py`
- `docs/tools/evaluate_hardware_log.py`
- `docs/tools/evaluate_field_ready_gate.py`
- `docs/tools/evaluate_all_hardware_logs.py`
- `docs/post-rc-backlog.md`

## RC1 Position

RC1 is suitable as a controlled software checkpoint.
It is not declared as final field-ready release until hardware-pending items are closed.
