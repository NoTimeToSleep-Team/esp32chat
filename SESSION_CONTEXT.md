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

Implemented:
- `LCS_EDITION` setting, default `camp`; `/health` exposes `edition`.
- `server/migrations/1001_camp_core.sql`: all camp tables, indexes,
  5 default playbooks (`missing_child`, `evacuation`, `medical`, `intruder`,
  `lockdown`), settings row per session.
- `server/app/camp/policy.py`: age bands, quiet hours 21:30–07:30,
  no child↔adult DMs, child DM opt-in/same band, media age+consent,
  forward restrictions, group scope, counselor request policy.
- `server/app/camp/service.py`: sessions, units, settings, people,
  import preview/commit with duplicate detection, badge generation,
  transfer, merge, 10-minute import undo, counselor request queue claim/close,
  audit, policy check.
- `server/app/camp/api.py`: `/camp` page placeholder and `/camp/api/*`
  endpoints for sessions/units/people/import/requests/settings/policy/audit.
- `main.py` includes camp router when `edition == "camp"`; `/camp/` no-store.
- Tests: `tests/unit/test_camp_policy.py`, `test_camp_service.py`.

Verification already run:
- `23 passed, 1 skipped` in `tests/unit`.
- Disposable FastAPI smoke via TestClient: `SMOKE_OK`; covers health,
  sessions, units, import, people, child request, counselor queue,
  claim/close, quiet-hours policy.

Commit: `5a374f5 feat(camp): add isolated camp foundation and request queue`.

## Cycle 2 — next implementation

Add to `service.py` and `api.py`, migration already has all tables:
1. Attendance: create/list/close event, mark present/absent/sick/medic/parent,
   all-present guard, missing list, overdue event detection.
2. Alerts: list playbooks, start alert/drill, acknowledge steps, close,
   list active/history.
3. Zones/scans: create zone, scan by badge/person, last seen, zone counters.
4. Duty/handover: create/list shifts, create handover with open items,
   acknowledge.
5. Pickup: create authorisation with QR, verify/checkout/checkin, restrictions.
6. Dietary: set/list/print.
7. Digest: staff create/update, parent sees only linked children.
8. Tests for all of the above + smoke.

Exact file locations:
- service: `server/app/camp/service.py`
- API: `server/app/camp/api.py`
- schema: `server/migrations/1001_camp_core.sql`
- tests: `tests/unit/test_camp_service.py`, new `test_camp_ops.py`
- local venv: `.\.venv\Scripts\python.exe`
- smoke: `C:\Windows\Temp\opencode\camp_smoke.py` (extend for cycle 2)

## Cycle 3 — after cycle 2

Role-based `/camp` UI (`server/app/static/camp/`), kiosk tokens + offline sync,
photo consent matrix, session report/CSV/HTML, `/camp/status`, docs
(trust/safety, legal templates, runbook, pilot metrics), full test pass,
final report.

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
4. Post passive agent-chat note (no wake) telling others to compact after their
   cycles. Our channel: `programmer@opencode` (session `ses_f448cfde7ffeFMnyiYRTqLDjAI`).
