# Field-Ready Gate

This document defines final go/no-go logic for moving from RC1 software baseline to field-ready status.

## Inputs

- Acceptance source: `docs/acceptance.md`
- Verification source: `docs/verification-report-2026-04-03.md`
- Hardware execution source: `docs/hardware-validation-checklist.md`
- Hardware run logs: `docs/hardware-validation-log-*.md`
- Known boundaries: `docs/known-limitations.md`

## Mandatory Gate Conditions

The release can be marked `field_ready=yes` only if all conditions are satisfied.

- `GATE-01` Software acceptance is green (`AC-SRV-*`, `AC-FW-*`, `AC-INT-*`, `AC-DOC-*`).
- `GATE-02` Hardware scenarios `AC-HW-01`..`AC-HW-04` are executed with no unresolved `fail`.
- `GATE-03` Every `blocked` hardware scenario has explicit owner + due date + mitigation path.
- `GATE-04` Known limitations are reviewed and any release-critical item is closed or accepted by owner.
- `GATE-05` Operator confirms safe-shutdown and incident handling drill evidence exists.

## Decision Matrix

| condition state | decision |
| --- | --- |
| all gate conditions satisfied | `GO` |
| one or more `fail` without approved mitigation | `NO-GO` |
| only `blocked` items with approved mitigation and accepted risk | `CONDITIONAL GO` |

## Signoff Block

- Candidate tag:
- Decision (`GO` / `NO-GO` / `CONDITIONAL GO`):
- Decision date:
- Technical owner:
- Operations owner:
- Risk summary:
- Required follow-up actions:

## Current Status Snapshot

- RC1 status: software baseline complete.
- Hardware package: prepared but not executed in this repository session.
- Current gate state: `NO-GO` for field-ready until hardware evidence is attached.

Optional evaluation helper:

```bash
python docs/tools/evaluate_hardware_log.py docs/hardware-validation-log-bootstrap.md
python docs/tools/evaluate_field_ready_gate.py --log docs/hardware-validation-log-bootstrap.md
python docs/tools/evaluate_all_hardware_logs.py
```
