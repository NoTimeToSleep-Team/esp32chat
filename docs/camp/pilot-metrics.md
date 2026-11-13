# Pilot metrics and acceptance

## Pilot shape (initial target)

- 1 camp, 1 session, 2 units, 40–60 children, 8–12 staff.
- 3-day pilot; measure daily, review after each day.
- 15-minute training for staff, on-site support for the first two days.

## Acceptance targets

| Metric | Target |
|---|---|
| Import 60 children + badges | < 20 minutes |
| Roll call 25 children | < 60 seconds |
| Alert acknowledgement visible to staff | < 60 seconds |
| Children with a badge/account | 100% |
| Manual duplicate accounts | 0 |
| Blocking failures during a shift | 0 |
| Missed/lost scans | < 1% |
| Session report + backup | completed every day |
| Purge plan ready | before the session ends |

## What to measure

- Time to create/import a session, units and badges.
- Roll-call duration per unit and unmarked rate at the deadline.
- Request queue: time to claim, time to close, reopened/duplicate rate.
- Alert: time to first acknowledgement, time to close, drill participation.
- Scan volume, stale kiosks, duplicate scans, offline queue replay count.
- Pickup: authorisations created, gate movements, overrides and reasons.
- Dietary records and print usage.
- Parent digest: created/sent ratio, parent access issues.
- Report export time and backup restore test result.
- Staff feedback: 1–5 usability score and top three friction points.

## Data to export

Use `GET /camp/api/report.csv` and `.html`; keep them with the backup manifest.
Do not put child names in the pilot review deck; aggregate only.

## Go / no-go

Continue only if:

- roll call is faster than paper or clearly less error-prone;
- every child is accounted for at every deadline;
- staff can open/close alerts without coaching;
- no child can see another family's digest;
- restore from backup has been tested;
- the director can explain retention and purge.

## Kill criteria

- Roll call is consistently slower than paper and causes missed children.
- Staff cannot acknowledge a live alert within the target.
- A child/parent sees data outside their scope.
- The system loses scans without a recoverable queue.
- On-site support is required for every shift beyond the pilot.
