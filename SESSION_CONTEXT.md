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
# 50 passed, 1 skipped
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

## UX/logic refinement (3 rounds)

- Round 1 `ab07cc5`: removed the token form, simplified role menus, Russian
  labels, light flat theme, role-scoped counselor lists, alert start/close
  permissions, faster rollcall, gate verify, digest sent state.
- Round 2 `01df325`: prep screen (session/units/import preview/commit/undo,
  guardian links, quiet hours), `/camp/api/staff`, incremental rollcall
  updates, session selection, import error text and 10-minute undo hint,
  pickup document sanitization.
- Round 3 `c96c04e`: fixed counselor import authorization, pickup unit scope,
  rollcall rollback on error, BOM removal, wrapper input validation.
- Logic agent verdict after round 3: PASS WITH FIXES; critical items fixed in
  `c96c04e`. Remaining noncritical: `roles_json` playbooks is data-only.
- Verification: `50 passed, 1 skipped`; `compileall`; `node --check`;
  disposable smoke `SMOKE_OK`; `bash -n` + `DRY_RUN=1` for AP scripts.
- GitHub: pushed local `main` to `github/camp-edition` at `5dd2e38`
  (https://github.com/NoTimeToSleep-Team/esp32chat/tree/camp-edition).

## Addendum: local Wi-Fi AP + captive portal

The app itself cannot broadcast Wi-Fi; added a host-side AP setup for the Pi:

- `server/scripts/configure_camp_ap.sh` — camp defaults (`CAMP-CHAT`, **open
  network, no password**, `192.168.50.1`, DHCP `.50–.150`, offline, local DNS).
- `server/scripts/camp_captive_portal.py` — port 80 responder; every HTTP
  request returns `302` to `http://192.168.50.1:18080/camp`; `/healthz` = 204.
- `configure_camp_ap.sh` installs/enables `camp-captive-portal.service`; no
  manual IP URL is needed on a phone (standard captive-portal sheet).
- `configure_pi_ap_nat.sh` — new `AP_OPEN` (open/WPA2), `AP_NAT_ENABLED=0`,
  `AP_DNS_SERVERS`, `AP_DNS_WILDCARD` offline mode; defaults unchanged.
- `/camp/status` returns `network` (SSID, portal URL, mode, internet, open,
  security, captive_portal, captive_url); `/camp` has a “Сеть” panel.
- `docs/camp/network.md` — install, verify, security, rollback, Bookworm
  NetworkManager caveat.

Verified locally: `bash -n` for scripts; `DRY_RUN=1` offline/NAT; captive portal
unit tests start a real loopback server and assert 302/204. Actual AP was not
hardware-tested from the Windows dev host.

## Temporary deployment on EvilPi5 (2026-11-13)

- Board `169.254.93.1` (SSH key `lc_board_ed25519`, user `gamecat`).
- Fixed `/home/gamecat/lc-network-boot.sh` fallback because the legacy DB was
  empty and hostapd got `interface=`. Backup:
  `/home/gamecat/lc-network-boot.sh.bak-camp-20261113192952`.
- AP is open `local-chat`, `wlan0=192.168.4.1/24`; `hostapd` + `dnsmasq`
  active.
- Camp Edition copied to `/home/gamecat/camp-edition`, runs on `18081` using
  `/opt/local-chat-server/.venv`; DB `data/sqlite/camp.db`; admin `camp`
  (temporary password kept out of the repo; change after demo).
  `camp.pid` / `camp.log`.
- Captive proxy: `lc-proxy` and `local-chat-proxy` services stopped; user proxy
  on `3128` started with `LC_SERVER_URL=http://192.168.4.1:18081/camp`;
  PID `proxy.pid`. It redirects to Camp Edition `/camp`; direct check:
  `curl -x http://127.0.0.1:3128 http://example.com/` → 302.
- Revert to main chat:
  `kill $(cat /home/gamecat/camp-edition/proxy.pid); sudo systemctl start lc-proxy`.
- Work laptop must NOT join `local-chat`: no internet on that AP.

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
