# Camp runbook

## 0. Before the session

- Set up the local Wi-Fi access point (`CAMP-CHAT`) on the Raspberry Pi by
  `server/scripts/configure_camp_ap.sh`; see `network.md`. Do this before
  staff arrive and keep a keyboard/console path to the Pi.
- Create the camp session and units.
- Import children/staff from the approved list; preview first, then commit.
- Confirm badges and print/attach them.
- Link parent profiles to children; verify a parent sees only their own child.
- Record dietary restrictions and pickup authorisations.
- Set quiet hours and media policy; collect photo consents.
- Create zones (gate, buildings, medical, checkpoints).
- Register kiosks per zone and label the physical devices.
- Take a database snapshot and test a restore on a spare copy.

## 1. Start of shift

1. Director opens `/camp`, selects the session and checks `/camp/status`.
2. Verify DB read/write, disk space, clock skew and kiosk `active/stale`.
3. Staff check the duty roster and the open handover items.
4. Acknowledge the handover; unresolved items stay open.

## 2. Roll call (target < 60 seconds for 25 children)

1. Counselor opens “Перекличка”, selects their unit, starts a roll call.
2. Scan badges or tap statuses (`present`, `absent`, `sick`, `medic`,
   `parent`, `left`).
3. “Все присутствуют” fills only unmarked children; it never overwrites an
   existing status.
4. Close the event. If someone is unmarked, the guard blocks the close; a
   forced close requires a reason and is audited.
5. Overdue events appear in “Перекличка” with an `overdue` badge.

## 3. Child request

1. Child taps “Позвать вожатого” and chooses a reason.
2. The request appears in the counselor queue; no free-form chat.
3. Counselor claims it, handles it and closes it with a note.
4. Never close a request without physically checking on the child.

## 4. Alert

1. Choose the playbook (missing child, evacuation, medical, intruder,
   lockdown) and start it; use “Учение” only for a planned drill.
2. Acknowledge step 0 to show visibility; the UI shows who acknowledged.
3. Follow the steps. Do not close until the site is safe.
4. Close with an after-action note; keep facts and times.
5. If the alert involved a child, record the linked person in the note/audit.

## 5. Zone scan / last seen

1. Staff or kiosk selects the zone and scans the badge.
2. `last seen` shows the latest zone; zone counters cover the last 120 minutes
   by default.
3. Scans are append-only; correct mistakes with a new scan, never edit history.
4. A lost kiosk must be revoked from “Киоск” immediately.

## 6. Pickup / gate

1. Create a pickup authorisation for a named adult; add restrictions if needed.
2. At the gate, scan or paste the QR into “Ворота”.
3. If restrictions are present, record an override reason and verify ID.
4. Record `out`; the child appears as “currently out”.
5. Record `in` on return. The same direction twice is a conflict.
6. Keep the printed authorisation and the gate log for the session audit.

## 7. Dietary

- Kitchen/medic add restrictions; the print view is the kitchen copy.
- Treat “без орехов” and similar as safety-critical; verify with the parent.
- Remove records only when the restriction is no longer valid, not to hide a
  mistake.

## 8. Parent digest

- Counselor/director writes a short factual digest per child per day.
- Parents see only linked children.
- Do not include other children's names, medical details or pickup secrets.
- Mark it sent after the actual delivery.

## 9. End of shift / end of session

1. Close open attendance events.
2. Close or hand over open requests/alerts; no silent backlog.
3. Acknowledge handover; list unresolved items.
4. Export CSV and HTML report.
5. Take a backup and record where it is stored.
6. After the retention period: export, verify backup, then purge.

## 10. Failure modes

- **DB read-only / disk full**: stop writes, switch to paper, free space,
  restore from snapshot if needed. Do not “fix” by deleting audit rows.
- **Clock wrong**: fix NTP/RTC; note the offset in the report; do not backdate
  safety events.
- **Kiosk offline**: queue scans locally; sync later with unique `op_id`.
  Scans are append-only; replays are idempotent.
- **Lost staff token**: revoke sessions, issue a new one, review audit.
- **Suspected data leak**: revoke access, preserve logs, notify director/DPO.

## 11. Quick commands

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\unit
.\.venv\Scripts\python.exe C:\Windows\Temp\opencode\camp_smoke.py
curl http://127.0.0.1:18081/camp/status
```

On the Pi:

```bash
sudo CAMP_AP_PASSPHRASE='...' bash server/scripts/configure_camp_ap.sh
systemctl status hostapd dnsmasq --no-pager
```
