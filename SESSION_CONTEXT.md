# SESSION_CONTEXT — Camp Edition

## Task

Implement the Camp Edition report as an **isolated branch-off** of
`LC_RELEASE`, in **3 development-check cycles**, without modifying the main
project or the live board. Compact and notify other agents after each cycle.

Source report:
`D:\opencode\LC_BACKUPS\camp-edition-deep-report-2026-11-13.md`

## Isolation

- Independent clone at `D:\opencode\LC_CAMP_EDITION` from `c2a7c53`.
- Do not modify `D:\opencode\LC_RELEASE` or board `18080`.
- Local `.venv` inside the camp project; `.venv/` is git-ignored.
- Local disposable test DB only.

## State after Cycle 1 (commit `5a374f5`)

- `LCS_EDITION` setting, default `camp`; `/health` and bootstrap expose `edition`.
- Migration `server/migrations/1001_camp_core.sql`: all camp tables, indexes,
  5 playbooks, settings row per session.
- `server/app/camp/policy.py`: age bands, quiet hours 21:30–07:30,
  no child↔adult DMs, child DM opt-in/same band, media age+consent,
  forward restrictions, group scope, counselor request policy.
- `server/app/camp/service.py`: sessions, units, settings, people,
  import preview/commit with duplicate detection, badge generation,
  transfer, merge, 10-minute import undo, counselor request queue claim/close,
  audit, policy check.
- `server/app/camp/api.py`: `/camp` placeholder and `/camp/api/*`.
- Tests: `test_camp_policy.py`, `test_camp_service.py`.

## State after Cycle 2

Added to `service.py` and `api.py`:

- Attendance: create/list/get, mark, all-present guard, close, overdue.
- Alerts: playbook list, start alert/drill, acknowledgements, after-action close.
- Zones/scans: create/list zones, append-only scan by badge/person,
  last-seen, 120-minute zone monitor, zone scan log.
- Duty/handover: create/list shifts, create/list handovers, acknowledge.
- Pickup: create/list/verify authorisations with QR and restrictions,
  gate movements, override reason, gate log.
- Dietary: upsert/list/remove, printable HTML view.
- Parent digest: guardian links, upsert/list/mark-sent; parents are forced
  to their own linked children.
- `_resolve_session_id` now enforces the actor's session; additional
  `_guard_session` checks on record-id endpoints.
- Migration changed only for `camp_alerts.after_action` and `closed_by`.

API groups (all under `/camp/api`, token as `session_token` query/header):

`attendance/events`, `attendance/overdue`, `alert-playbooks`, `alerts`,
`zones`, `zones/monitor`, `zones/{id}/scans`, `scans`, `people/{id}/last-seen`,
`duty`, `handovers`, `pickup`, `pickup/verify`, `movements`, `dietary`,
`dietary/print`, `guardians`, `digests`, `digests/sent`.

Verification after Cycle 2:
- `30 passed, 1 skipped` in `tests/unit` (7 new ops tests).
- Extended disposable TestClient smoke: `SMOKE_OK`; covers attendance,
  alarms, zones/scans, duty/handover, pickup/movement, dietary print, parent digest.

## Cycle 3 — next implementation

Cycle 3 is not started. Do it in this order:

1. **Role-based `/camp` UI**
   - `server/app/static/camp/camp.html` (token gate, nav by actor role)
   - `server/app/static/camp/camp.css`
   - `server/app/static/camp/camp.js` (fetch `/camp/api/me`; render panels)
   - Panels: child (request button, own attendance/digest), counselor
     (roll call, request queue, scan, handover), director (sessions/import,
     alerts, duty, report, settings), security (gate/pickup/scans/alerts),
     medic (alerts/dietary), parent (own children/digests).
2. **Kiosk / offline**
   - Add `CampService.create_kiosk`, `list_kiosks`, `revoke_kiosk`,
     `kiosk_scan` (token hash, scopes, revoke) using `camp_kiosks`.
   - Add `sync_offline` using `camp_sync_ops` with idempotent `op_id`.
   - Kiosk token is returned once; store only SHA-256 hash.
3. **Photo consent**
   - Add service methods for `camp_consents`: set/get, consent matrix,
     enforce media policy from policy.py. `internal_chat`, `parent_digest`,
     `promo`, `none`.
4. **Report/status**
   - `session_report` aggregates counts (children, units, attendance,
     requests, scans, alerts, dietary, digest).
   - CSV and HTML print endpoints.
   - `/camp/status`: DB write, disk free, clock drift, backup hint.
5. **Docs**
   - `docs/camp/README.md`, `trust-safety.md`, `runbook.md`,
     `legal-templates.md`, `pilot-metrics.md`, `api.md`.
6. **Final**: full pytest, compileall, extended smoke, final summary,
   update `PLAN.md`, commit, compact, notify agent-chat.

## Commands

```powershell
cd D:\opencode\LC_CAMP_EDITION
.\.venv\Scripts\python.exe -m pytest -q tests\unit
.\.venv\Scripts\python.exe -m compileall -q server\app
.\.venv\Scripts\python.exe C:\Windows\Temp\opencode\camp_smoke.py
```

## Compact / notify

After each cycle:
1. Update `PLAN.md` and this file.
2. Commit logical changes.
3. Run `opencode-compact --force`.
4. Post passive agent-chat note telling others to compact after their cycles.
   Our channel: `programmer@opencode`
   (session `ses_f448cfde7ffeFMnyiYRTqLDjAI`).
