# Business-logic P0 cleanup — 2026-11-10

Fixes the four P0 items from the business-logic review of `LC_RELEASE` v0.1.10.

## P0-1 — cleanup routes

`server/app/static/admin.html` called `/chat/api/admin/delete-chats` and
`/delete-users`, while the API exposes `/delete-all-chats` and
`/delete-all-users`. The UI now uses the real routes. The labels also state
that the common chat is kept and that only non-admin users are deleted.

## P0-2 — legacy static pages

`server/app/static/devices/devices.js` had a stray `activeDeviceId` block after
the init IIFE; `activeDeviceId` now lives in `state`. `rfid.js` had a stray
closing `};`. Both pass `node --check`.

`/rfid` remains intentionally deprecated and blocked by
`security/infrastructure.py`; the router was already not mounted. The static
file is kept for reference and is not a browser-reachable surface.

## P0-3 — full reset

`ChatService.full_reset()` now:

- clears blog posts, support messages/tickets, chat data, chats (keeping the
  common chat row), device pairings and applications;
- deletes non-admin users;
- preserves the current admin session; other sessions are revoked;
- returns `deleted_count` plus per-area counters.

The admin UI asks for a typed `RESET` confirmation, then the normal confirm, and
shows the returned count. The API also requires `confirm_phrase: "RESET"` on the
server, so a bare `{confirm: true}` request is rejected. The confirmation text
no longer promises data the service does not clear.

## P0-4 — delete all users

`delete_all_users()` now deletes `users WHERE role != 'admin'`, so every admin
survives, not only the caller. Blog posts, device-catalog entries, RFID cards,
device-blacklist entries and edge-node deployments created by deleted users are
reassigned to the acting admin before user deletion to satisfy the
`ON DELETE RESTRICT` foreign keys. Non-admin sessions and device pairings are
removed first. `full_reset()` performs the same blacklist/deployment reassignment
before deleting non-admin users.

## Verification

- New suite: `tests/server/test_business_logic_p0_2026_11_10.py` — **32/32**.
- Existing server suites: `09d` 29/29, `09c` 38/38, `09b` 20/20, access 38/38,
  admin boundary 26/26, chat updates 10/10.
- UI: admin 13/13, devices 19/19, ui_test 24/24.
- `node --check` for both legacy JS files — PASS.

Remaining P1/P2 items and the product-model questions from the second
business-logic review are intentionally out of this P0 commit.
