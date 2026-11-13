# Camp Edition development plan

Source: `D:\opencode\LC_BACKUPS\camp-edition-deep-report-2026-11-13.md`
Base: `LC_RELEASE` @ `c2a7c53`
Isolation: this directory only; `LC_RELEASE` and live board untouched.

## Cycle 1 — foundation and safe communication — DONE

- [x] `LCS_EDITION=camp` + `/health` edition field
- [x] migration `1001_camp_core.sql` (all camp tables + five alert playbooks)
- [x] `CampService`: sessions, units, people, import preview/commit/merge/transfer/undo
- [x] age bands, quiet hours, DM/media/forward policy
- [x] counselor request queue (child cannot free-DM staff)
- [x] tests: policy + import + request queue (13 camp tests; 23 unit total pass)
- [x] local disposable server smoke (`SMOKE_OK`)
- [x] commit `5a374f5`; compact + notify room

## Cycle 2 — shift operations — DONE

- [x] attendance events, deadline, marks, all-present guard, overdue alerts
- [x] alert playbooks, drill mode, acknowledgements, after-action
- [x] zones and append-only scans, last-seen, zone counters
- [x] duty roster, handover checklist and acknowledgement
- [x] pickup authorisations, gate movements, restrictions
- [x] dietary list and print view
- [x] parent digest (own child only)
- [x] tests + compact + notify room (30 unit pass + extended smoke)

## Cycle 3 — UI, kiosk, resilience and product docs — DONE

- [x] role-based `/camp` SPA (child, counselor, director, security, medic, parent)
- [x] kiosk mode, token revoke, offline queue sync endpoint
- [x] photo consent matrix and forward restrictions
- [x] session report + CSV/HTML print
- [x] `/camp/status` checks (DB read/write, quick_check, disk, clock, kiosk stale)
- [x] trust/safety, legal templates, runbook, pilot metrics, API docs
- [x] 36 unit tests pass, compileall, node syntax check, extended disposable smoke
- [x] final commit; compact + notify room

### Addendum: local Wi-Fi AP

- [x] `server/scripts/configure_camp_ap.sh`: `CAMP-CHAT`, WPA2, offline,
  `192.168.50.1`, DHCP, local DNS, optional NAT
- [x] `configure_pi_ap_nat.sh`: `AP_NAT_ENABLED`, `AP_DNS_SERVERS`,
  `AP_DNS_WILDCARD` offline mode
- [x] `/camp/status` network block + `/camp` “Сеть” panel
- [x] `docs/camp/network.md` and runbook/API/README updates

## Verification

```powershell
cd D:\opencode\LC_CAMP_EDITION
.\.venv\Scripts\python.exe -m pytest -q tests\unit
.\.venv\Scripts\python.exe -m compileall -q server\app
node --check server/app/static/camp/camp.js
.\.venv\Scripts\python.exe C:\Windows\Temp\opencode\camp_smoke.py
```

## Acceptance ideas from report

- import 60 children + badges < 20 min (preview/commit, badge generation)
- roll call 25 children < 60 s
- alert acknowledgement visibility < 60 s
- zero blocking failures, zero manual accounts
- end-of-shift export + purge plan
- no GPS, face recognition, public galleries, child-facing AI
