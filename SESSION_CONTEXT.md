# SESSION_CONTEXT — Camp Edition

## Task

Implement the Camp Edition report as an **isolated branch-off** of
`LC_RELEASE`, in **3 development-check cycles**, without modifying the main
project or the live board. Compact and notify other agents after each cycle.

Source report:
`D:\opencode\LC_BACKUPS\camp-edition-deep-report-2026-11-13.md`

## Isolation

- Independent clone at `D:\opencode\LC_CAMP_EDITION` from `c2a7c53`.
- `D:\opencode\LC_RELEASE` and board `18080` were not modified.
- Local `.venv` inside the camp project; `.venv/` is git-ignored.
- Local disposable test DB/server only.

## Final state

All three cycles are complete.

### Cycle 1 (commit `5a374f5`)

- `LCS_EDITION` default `camp`; `/health` exposes edition.
- Migration `1001_camp_core.sql`: camp tables, indexes, five playbooks,
  settings, audit, kiosk/sync/consent tables.
- `server/app/camp/policy.py`: age bands, quiet hours 21:30–07:30,
  no child↔adult DMs, child DM opt-in/same band, media age+consent,
  forward restrictions, group scope, counselor request policy.
- Sessions, units, settings, people, import preview/commit/merge/transfer/undo,
  badge generation, counselor request queue, audit, policy checks.

### Cycle 2 (commit `253ccc9`)

- Attendance create/list/get/mark/all-present/close/overdue.
- Alerts: playbook list, start alert/drill, ack, after-action close.
- Zones/scans: create/list, append-only scan, last-seen, monitor.
- Duty/handover: shifts, create/list/ack handover.
- Pickup: QR authorisations, restrictions, gate movements, gate log.
- Dietary: upsert/list/remove + printable HTML.
- Parent digest: guardian links, digest list scoped to linked children.
- Session guards on record-id endpoints.
- Migration adds `camp_alerts.after_action`, `camp_alerts.closed_by`.

### Cycle 3 (final `main` HEAD, see `git log --oneline -1`)

- Role-based `/camp` SPA:
  `server/app/static/camp/camp.html`, `camp.css`, `camp.js`.
- Kiosk tokens: `create_kiosk`, `list_kiosks`, `revoke_kiosk`, `kiosk_scan`;
  raw token returned once; only SHA-256 stored; scoped to one zone/scan.
- Offline sync `sync_offline` + `POST /camp/api/sync`: idempotent `op_id`,
  supports `scan` and `attendance_mark`; replays return `replayed: true`.
- Consent matrix: `set_consent`, `get_consents`, `consent_matrix`,
  `consent_allows`; parent linked-child enforcement.
- Session report: `session_report`, `report_csv`, `report_html`
  (JSON/CSV/HTML print).
- `system_status` + public `GET /camp/status`: DB read/write, quick_check,
  disk free, clock skew, sessions, kiosk stale, backup hint.
- Docs: `docs/camp/README.md`, `trust-safety.md`, `runbook.md`,
  `legal-templates.md`, `pilot-metrics.md`, `api.md`.

## Verification (final)

```powershell
cd D:\opencode\LC_CAMP_EDITION
.\.venv\Scripts\python.exe -m pytest -q tests\unit
# 36 passed, 1 skipped
.\.venv\Scripts\python.exe -m compileall -q server\app
node --check server/app/static/camp/camp.js
.\.venv\Scripts\python.exe C:\Windows\Temp\opencode\camp_smoke.py
# SMOKE_OK
```

The extended disposable smoke covers health/session/units/import/people,
request queue, policy, attendance, alerts, zones/scans, duty/handover,
pickup/gate, dietary print, parent digest, consent matrix, kiosk create/scan/
revoke, offline sync replay, report JSON/CSV/HTML, `/camp/status`, and static
UI files.

## Addendum: local Wi-Fi AP

The app itself cannot broadcast Wi-Fi; added a host-side AP setup for the Pi:

- `server/scripts/configure_camp_ap.sh` — camp defaults (`CAMP-CHAT`, WPA2,
  `192.168.50.1`, DHCP `.50–.150`, offline, local DNS/captive portal).
- `server/scripts/configure_pi_ap_nat.sh` — new `AP_NAT_ENABLED=0`,
  `AP_DNS_SERVERS`, `AP_DNS_WILDCARD` offline mode; defaults unchanged.
- `/camp/status` returns `network` (SSID, portal URL, mode, internet,
  security); `/camp` has a “Сеть” panel for director/security/IT.
- `docs/camp/network.md` — install, verify, security, rollback, Bookworm
  NetworkManager caveat.

Verified locally: `bash -n` for both scripts; `DRY_RUN=1` for offline and NAT
modes completed with expected commands. Actual AP was not hardware-tested here
(no Raspberry Pi/AP interface on the Windows dev host); deployment verification
must be done on the target Pi.

## Commands / env

```powershell
cd D:\opencode\LC_CAMP_EDITION
$env:LCS_EDITION = "camp"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir server --port 18081
```

Use only disposable local DB; do not point at live board data.

## Compact / notify

After the final commit:
1. `opencode-compact --force`.
2. Passive agent-chat note to room `global` from `programmer@opencode`.
3. Our session: `ses_f448cfde7ffeFMnyiYRTqLDjAI`.
