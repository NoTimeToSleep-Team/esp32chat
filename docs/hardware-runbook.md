# Hardware Runbook

Practical sequence for executing one physical validation session.

## Pre-Run

1. Confirm server node identity (Raspberry Pi is main server).
2. Prepare a session log from bootstrap or generate a new one.
3. Record device matrix and firmware references.
4. Start server and verify base health.

Session log generator:

```bash
python docs/tools/new_hardware_log.py --build-tag RC1
```

Recommended quick checks:

```bash
python -m firmware.common.protocol.verify_contract_samples
python -m firmware.integration.verify_chat_e2e
python -m firmware.integration.verify_ops_e2e
```

## Run Sequence

1. Execute `HW-ENV-*` scenarios from `docs/hardware-validation-checklist.md`.
2. Execute network scenarios `HW-NET-*`.
3. Execute power/thermal scenarios `HW-PWR-*`.
4. Execute operator scenarios `HW-OPS-*`.
5. Execute safe-shutdown scenarios `HW-SAFE-*`.

For each scenario:

- set result (`pass`/`fail`/`blocked`),
- attach evidence pointer,
- add concise note.

## Post-Run

1. Summarize counts: pass/fail/blocked.
2. Create follow-up list for every `fail` and `blocked` item.
3. Update `docs/field-ready-status.md` with latest gate snapshot.
4. Apply final decision in `docs/field-ready-gate.md` signoff block.

Optional helper:

```bash
python docs/tools/evaluate_hardware_log.py docs/hardware-validation-log-bootstrap.md
python docs/tools/evaluate_field_ready_gate.py --log docs/hardware-validation-log-bootstrap.md
python docs/tools/evaluate_all_hardware_logs.py
```

## Escalation Rule

- Any unresolved `fail` in `AC-HW-*` keeps field-ready decision at `NO-GO`.
- `CONDITIONAL GO` requires explicit mitigation owner and due date for each `blocked` item.
