# Camp API

All routes are mounted only when `LCS_EDITION=camp`.

- Web UI: `GET /camp` and `GET /camp/`
- Public status: `GET /camp/status`
- JSON base: `/camp/api`
- Auth (except kiosk scan and status): `session_token` query parameter or the
  normal web session token, validated as `ClientKind.WEB`
- Camp membership is resolved from `camp_people`; an admin user without a camp
  profile is treated as bootstrap `director`.

Errors use:

```json
{"detail": {"code": "role_forbidden", "message": "...", "details": {}}}
```

## Sessions, units, people

| Method | Path | Notes |
|---|---|---|
| GET | `/api/me` | Actor, sessions, current session, settings, units |
| GET/POST | `/api/sessions` | Create/list camp sessions |
| GET/POST | `/api/units` | Create/list units |
| GET | `/api/people` | Session/unit/role/search filter; parent scope enforced |
| GET | `/api/people/{id}` | Person detail |
| POST | `/api/people` | Create person |
| POST | `/api/import/preview` | Preview import rows |
| POST | `/api/import/commit` | Commit a preview |
| POST | `/api/import/{batch_id}/undo` | 10-minute undo |
| POST | `/api/people/{id}/transfer` | Unit transfer |
| POST | `/api/people/merge` | Merge duplicate profiles |

## Safety policy and communication

| Method | Path | Notes |
|---|---|---|
| GET/PATCH | `/api/settings` | Quiet hours/media/DM settings |
| POST | `/api/policy/check` | `direct_message`, `media`, `forward`, `post`, `group` |
| GET/POST | `/api/requests` | Child request queue |
| POST | `/api/requests/{id}/claim` | Counselor claim |
| POST | `/api/requests/{id}/close` | Close with note |
| GET | `/api/audit` | Director only |

## Attendance

| Method | Path | Notes |
|---|---|---|
| POST/GET | `/api/attendance/events` | Create/list roll calls |
| GET | `/api/attendance/events/{id}` | Detail + marks/missing |
| POST | `/api/attendance/events/{id}/marks` | `present`, `absent`, `sick`, `medic`, `parent`, `left` |
| POST | `/api/attendance/events/{id}/all-present` | Fill only unmarked |
| POST | `/api/attendance/events/{id}/close` | Guard; `force` + reason |
| GET | `/api/attendance/overdue` | Open events past deadline |

## Alerts

| Method | Path | Notes |
|---|---|---|
| GET | `/api/alert-playbooks` | Five default playbooks |
| GET/POST | `/api/alerts` | List/start alert or drill |
| GET | `/api/alerts/{id}` | Steps + acknowledgements |
| POST | `/api/alerts/{id}/ack` | Acknowledge step |
| POST | `/api/alerts/{id}/close` | Note + `after_action` |

## Zones and scans

| Method | Path | Notes |
|---|---|---|
| POST/GET | `/api/zones` | Create/list zones |
| GET | `/api/zones/monitor` | Scan/people counts in window |
| POST | `/api/scans` | Staff scan by badge or person |
| GET | `/api/zones/{id}/scans` | Append-only scan log |
| GET | `/api/people/{id}/last-seen` | Latest scan |

## Duty and handover

| Method | Path | Notes |
|---|---|---|
| POST/GET | `/api/duty` | Create/list shifts |
| POST/GET | `/api/handovers` | Create/list handover |
| POST | `/api/handovers/{id}/ack` | Receiver/director only |

## Pickup and gate

| Method | Path | Notes |
|---|---|---|
| POST/GET | `/api/pickup` | Create/list authorisations |
| GET | `/api/pickup/verify` | Verify QR |
| POST/GET | `/api/movements` | Record/list gate movements |

## Dietary, guardians, digest

| Method | Path | Notes |
|---|---|---|
| POST/GET/DELETE | `/api/dietary` | Upsert/list/remove |
| GET | `/api/dietary/print` | Printable HTML |
| POST/GET | `/api/guardians` | Link/list parent-child |
| POST/GET | `/api/digests` | Upsert/list; parent scope enforced |
| POST | `/api/digests/sent` | Mark delivered |

## Consent, kiosk, sync

| Method | Path | Notes |
|---|---|---|
| POST/GET | `/api/consents` | Set/get child consent |
| GET | `/api/consents/matrix` | Staff matrix |
| POST/GET | `/api/kiosks` | Create/list; raw token returned once |
| POST | `/api/kiosks/{id}/revoke` | Revoke immediately |
| POST | `/api/kiosk/scan` | Kiosk token only; no web token |
| POST | `/api/sync` | Idempotent offline operations |

Offline operation envelope:

```json
{
  "device_id": "offline-tablet",
  "operations": [
    {
      "op_id": "uuid-or-device-counter",
      "kind": "scan",
      "payload": {"zone_id": 1, "person_id": 5},
      "client_at_ms": 1760000000000
    }
  ]
}
```

Supported `kind`: `scan`, `attendance_mark`. Replayed `op_id` returns the
original status with `replayed: true`. Scans are append-only.

## Report and status

| Method | Path | Notes |
|---|---|---|
| GET | `/api/report` | Aggregated JSON |
| GET | `/api/report.csv` | UTF-8 BOM CSV attachment |
| GET | `/api/report.html` | Print-friendly HTML |
| GET | `/camp/status` | DB read/write, quick_check, disk, clock, kiosks, network |

`/camp/status` also returns the configured AP view:

```json
{
  "network": {
    "ssid": "CAMP-CHAT",
    "address": "192.168.50.1",
    "portal_url": "http://192.168.50.1:18080/camp",
    "mode": "offline",
    "internet": false,
    "security": "WPA2-PSK"
  }
}
```

It reflects `CAMP_AP_*` environment values on the server process, not a live
`hostapd` probe. Host-level AP setup is documented in `network.md`.

## Kiosk flow

1. Director/security creates a kiosk for a zone.
2. Copy the returned token to the device once; the server stores only SHA-256.
3. Device calls `POST /camp/api/kiosk/scan?kiosk_token=...` with a badge or
   person id.
4. Revoke a lost device; revoked tokens receive `403 kiosk_revoked`.
