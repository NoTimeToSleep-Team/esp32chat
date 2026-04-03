# Post-RC Backlog

Prioritized backlog after RC1 software baseline.

## P0 - Field-Ready Blocking

- Execute physical validation scenarios `AC-HW-01`..`AC-HW-04`.
- Collect complete evidence package in hardware log.
- Resolve any `fail` outcomes before field-ready signoff.

## P1 - Reliability and Operations

- Add stressed multi-node realtime chat test profile.
- Add sustained-run monitoring report template (power/thermal/network).
- Expand operator drills for incident escalation and rollback paths.

## P2 - Hardening

- Review authentication/session edge cases under high retry pressure.
- Expand security audit/event coverage for admin-sensitive flows.
- Perform external security review planning (scope, timeline, owner).

## P3 - Release Process Hygiene

- Initialize git repository and establish branch/release conventions.
- Define changelog and release-note policy for subsequent RCs.
- Add repeatable CI workflow for software verification sweep. (`done`: `.github/workflows/software-verification.yml`)

## Tracking Notes

- This backlog does not override current known limitations.
- Field-ready decision remains governed by `docs/field-ready-gate.md`.
