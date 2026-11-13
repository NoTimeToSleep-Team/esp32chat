# SESSION_CONTEXT — Camp Edition

## Task

User asked: when the improvement agent sends the Camp Edition report, implement
everything as an **isolated branch-off**, not touching the main
`LC_RELEASE` project, in **3 development-check cycles**, and compact after
each cycle. The report is at:

`D:\opencode\LC_BACKUPS\camp-edition-deep-report-2026-11-13.md`

## Isolation decision

- Source repo cloned from `D:\opencode\LC_RELEASE` at `c2a7c53` into
  `D:\opencode\LC_CAMP_EDITION`.
- The clone is an independent repo; no branch was created in the main repo
  (main project policy says only `main` + tags there).
- Never modify `D:\opencode\LC_RELEASE` or deploy to the live board.
- Work only inside `D:\opencode\LC_CAMP_EDITION`.
- New `AGENTS.md` and `PLAN.md` describe the isolated scope.
- No secrets, no live data, no destructive tests.

## Current state — Cycle 1 in progress

Completed:
- Cloned repo at `c2a7c53`.
- Added `AGENTS.md` and `PLAN.md`.
- Added migration:
  `server/migrations/1001_camp_core.sql`
  It contains the full schema for all 18 mechanics:
  sessions, units, people, guardians, settings, requests, attendance events /
  marks, alert playbooks / alerts / acks, zones / scans, pickup auth /
  movements, consents, digest, dietary, duty shifts, handover, import batches,
  audit, kiosks, sync ops; plus five default playbooks and default settings.
- No Python camp code yet; no tests yet.

Not done yet:
- `LCS_EDITION` config and `/health` edition field.
- `server/app/camp/` package.
- `CampService` and API router.
- Role-based `/camp` UI.
- Tests and local smoke server.

## Next steps (Cycle 1)

1. Add `edition` to `Settings` (`LCS_EDITION`, default `camp` in this copy);
   expose in `/health`; include camp router in `main.py`.
2. Build `server/app/camp/`:
   - `policy.py`: age bands `<10`, `10_13`, `14_17`, `adult`; quiet hours
     21:30–07:30; no child↔staff free DMs by default; media/forward rules.
   - `service.py`: sessions, units, people, import preview/commit with
     duplicate detection, merge/transfer/undo, request queue (claim/close),
     audit.
   - `api.py`: `/camp/api/*` endpoints, `/camp` page.
3. Add unit tests for policy, import/duplicates, request queue.
4. Run `pytest`, `compileall`, a disposable local server smoke.
5. Mark Cycle 1 done in `PLAN.md`, run `opencode-compact --force`, and post a
   passive agent-chat note telling other agents to compact after their cycle.

Then Cycle 2 (attendance, alerts, zones, duty/handover, pickup, dietary,
digest) and Cycle 3 (UI, kiosk/offline sync, photo consents, report/status,
docs, full tests).

## Repo facts

- Base commit: `c2a7c53`.
- Python venv for tests can be reused from:
  `D:\opencode\LC_RELEASE\server\.venv\Scripts\python.exe`
  while working dir is `D:\opencode\LC_CAMP_EDITION\server`.
- Existing core app has `connect_sqlite()` in `app/db/connection.py`, which
  returns a `ClosingConnection`; use it for camp DB access.
- Existing API auth uses `X-Session-Token` / `session_token`; `AuthService`
  resolves web sessions.
- `app/main.py` includes routers near the bottom; add camp router only when
  `settings.edition == "camp"`.
- Static files are under `server/app/static/`; camp UI goes to
  `server/app/static/camp/`.
- Tests: `tests/unit` with `conftest.py` adding `server` to `sys.path`.

## Verification commands

```powershell
cd D:\opencode\LC_CAMP_EDITION
& D:\opencode\LC_RELEASE\server\.venv\Scripts\python.exe -m pytest -q tests\unit
& D:\opencode\LC_RELEASE\server\.venv\Scripts\python.exe -m compileall -q server\app
```

Disposable server: copy `server/config/test.env.example`, set temp
`LCS_DATABASE_URL`/`LCS_STORAGE_ROOT`, port 18084, start uvicorn, smoke
`/health` and `/camp/api/...`, then stop. Do not use live board.

## Agent-chat note to post after compaction

Room `lc-release`, passive (`post`, not `wake`), from `programmer`:

> Camp Edition: cycle 1 context saved and compacted. Multi-cycle work is
> isolated in D:\opencode\LC_CAMP_EDITION; LC_RELEASE/live board untouched.
> Please compact your own context after the current cycle too.

Also post the same note to `global` from `programmer@opencode` if useful.
