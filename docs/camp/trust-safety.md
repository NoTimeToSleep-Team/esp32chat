# Trust & safety

Camp Edition is a safety tool, not a surveillance tool.

## Non-goals and hard limits

- No GPS tracking, geofencing or location history.
- No facial recognition, biometric identification or emotion analysis.
- No public galleries or public child profiles.
- No child-facing AI companion or autonomous moderation of child messages.
- No free-form child ↔ adult direct messages; children use the counselor
  request queue.
- No secret cameras, hidden microphones or “smart” toys.

## Data minimization

- Store only what a shift needs: name, unit, room, badge, age band, role,
  dietary restrictions, pickup authorisations and operational events.
- Badges are identifiers, not medical records.
- Scans are append-only and used for last-seen/counters; they are not a
  continuous location trail.
- Import files should be deleted from the operator laptop after commit.
- Audit events keep actor, action, optional person id, and JSON details.

## Consent matrix

| Kind | Meaning | Default |
|---|---|---|
| `internal_chat` | Staff may share a child's photo/media inside camp chat | off |
| `parent_digest` | Photo may appear in the parent-visible digest | off |
| `promo` | Photo may be used for public/promo materials | off |
| `none` | Explicit refusal / do not use | off |

A missing row means **not granted**. Consent is attached to a child profile;
parents may set it only for their linked children. Staff can see the matrix,
but should not silently flip it for a parent.

## Access rules

- Director: full camp configuration, reports, kiosk management, audit.
- Counselor: own unit roll call, requests, handover, scans; own-unit child
  access.
- Security: gates, pickup, scans, alerts, zones.
- Medic: alerts, dietary, scans.
- Kitchen: dietary list only.
- Parent: linked children and digests only.
- Child: own day, own unit roll-call view, request queue.

Session tokens are bearer tokens. Use HTTPS at the edge, do not put them in
public links, and revoke/rotate them after staff turnover.

## Alerts and drills

- A real alert of the same kind cannot be opened twice at once; close the first
  one explicitly.
- Drills are marked `drill=1` and are excluded from “real” alert counts by
  operators.
- Acknowledge the current step, then close with an after-action note.
- Never use a drill to test on children without the director's approval and a
  prior briefing.

## Incidents

1. Make the site safe first; call emergency services if needed.
2. Open the relevant playbook and acknowledge.
3. Record facts, times, people and decisions in the after-action note.
4. Preserve the database and relevant audit rows.
5. Notify the director/DPO; follow local child-protection reporting duties.
6. Do not post details or photos in general chat.

## Retention and purge

- Each session has `retention_days` (default 30).
- Export the session report, then purge camp tables according to policy.
- Keep backups only as long as legally required and store them off-device.
- A purge is manual in this build; do a dry-run/backup before deleting data.

## Security checklist

- [ ] Change default admin credentials.
- [ ] HTTPS/reverse proxy at the edge.
- [ ] Session tokens short-lived and rotated after staff changes.
- [ ] Kiosks scoped to one zone; revoke lost devices immediately.
- [ ] Backups encrypted at rest and tested for restore.
- [ ] No sensitive data in screenshots, chat or issue trackers.
