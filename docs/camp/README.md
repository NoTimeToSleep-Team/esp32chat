# Camp Edition

Camp Edition is an isolated, additive offshoot of `LC_RELEASE` for running a
small offline-first camp: roll call, child-safe requests, alerts, zones,
pickup, dietary needs and parent digests.

- Base: `LC_RELEASE` commit `c2a7c53`
- Working copy: this directory only
- Status: development/pilot; not deployed to the live board
- Entry point: `/camp` (web UI) and `/camp/api/*` (JSON)
- Edition switch: `LCS_EDITION=camp`

## What is included

- Camp sessions, units, people, CSV/JSON import with preview, merge, transfer
  and 10-minute undo.
- Child request queue instead of free child ↔ adult direct messages.
- Age/quiet-hours/media/forward policy checks.
- Attendance with deadlines, all-present guard, missing list and overdue
  detection.
- Alert playbooks (`missing_child`, `evacuation`, `medical`, `intruder`,
  `lockdown`), drills, acknowledgements and after-action notes.
- Append-only zone scans, last-seen lookup and zone counters.
- Duty shifts, handover checklist and acknowledgement.
- Pickup QR authorisations, restrictions, gate movements and gate log.
- Dietary list + printable view.
- Parent digest restricted to linked children.
- Photo consent matrix (`internal_chat`, `parent_digest`, `promo`, `none`).
- Single-use kiosk tokens (only a SHA-256 hash is stored) and revoke.
- Idempotent offline sync endpoint for scans and attendance marks.
- Session report (JSON/CSV/HTML), role-based UI and `/camp/status`.
- Camp Wi-Fi access point helper (`CAMP-CHAT`, open network, offline,
  captive portal, no NAT by default); see `network.md`.

## Run locally

```powershell
cd D:\opencode\LC_CAMP_EDITION
$env:LCS_EDITION = "camp"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir server --port 18081
```

Do not run a foreground server in an automated shell without a timeout. The
project-local `.venv` is used for tests and smoke checks.

## Verify

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\unit
.\.venv\Scripts\python.exe -m compileall -q server\app
.\.venv\Scripts\python.exe C:\Windows\Temp\opencode\camp_smoke.py
```

## Security notes

- Camp routes require a normal web session token.
- A kiosk token is limited to `scan` and one zone; its raw value is returned
  once and never stored.
- Parents only see linked children and their digests.
- No GPS, facial recognition, public photo gallery or child-facing AI.
- See `trust-safety.md`, `runbook.md`, `legal-templates.md`, `pilot-metrics.md`
  and `api.md`.
