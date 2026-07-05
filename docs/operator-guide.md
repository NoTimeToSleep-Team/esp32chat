# Operator Guide

This guide defines baseline operator workflow for local deployment and maintenance.

Stage reference: `v0.16.02`.

## 1. Startup Baseline

- Ensure Raspberry Pi is the only main server node.
- Confirm configuration profile and storage paths before startup.
- Validate `/health` endpoint after service launch.

## 2. Access and Roles

- Use admin account only for administrative actions.
- Keep hardware client flow non-guest.
- Use role-scoped APIs for moderation/content/support actions.

## 3. Daily Operational Checks

- Verify auth/login path is healthy.
- Verify chat/blog/support API responsiveness.
- Check runtime state and telemetry endpoints for internal service nodes.

Recommended software checks:

```bash
python -m firmware.common.protocol.verify_contract_samples
python -m firmware.integration.verify_chat_e2e
python -m firmware.integration.verify_ops_e2e
```

## 4. Content and Support Operations

- Blog publishing: `POST /admin/content/blog/posts`.
- Support queue review: `GET /admin/content/support/tickets`.
- Support reply/status: `/admin/content/support/tickets/{ticket_id}/reply` and `/status`.

## 5. Device Runtime Operations

- Register/heartbeat/telemetry/status flow is available under `/ops/api/devices/*`.
- Treat missing heartbeat as degraded device connectivity signal.

## 6. Safe Shutdown Principle

- Do not force power-off when graceful shutdown path is available.
- Prefer safe sequence: stop new sessions, flush writes, complete shutdown flow.
- Validate service state after reboot before restoring normal operator load.

## 7. Incident Handling (Minimum)

- Record incident type, timestamp, affected role/device, and observed impact.
- Keep evidence of API responses and logs for replay/debug.
- Avoid ad-hoc config changes without rollback notes.

## 8. Known Boundaries

- Software verifier success does not replace physical hardware acceptance.
- Devices without storage are limited to constrained offline behavior.
- Any unverified capability must remain marked as pending.

## 9. Hardware Validation Package

- Execute hardware queue using `docs/hardware-validation-checklist.md`.
- Record every scenario using `docs/hardware-validation-log-template.md`.
- Treat any `fail`/`blocked` item as release gate input, not as informal note.
- Use `docs/hardware-validation-log-bootstrap.md` as the first ready-to-fill run sheet.
- Optionally generate dated logs via `docs/tools/new_hardware_log.py`.
- Make final field decision using `docs/field-ready-gate.md`.
- Follow execution order from `docs/hardware-runbook.md`.
- Use `docs/tools/evaluate_all_hardware_logs.py` to review latest dated hardware session status.
