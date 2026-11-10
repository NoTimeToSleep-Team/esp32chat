# Business-logic P1/P2/P3 fixes — 2026-11-10

Follow-up to the live logic review. The P0 cleanup is in `eb2f3d3`; this pass
addresses the access-control and consistency findings that were confirmed by
HTTP scenarios.

## P1-1 — a coded private room can no longer be published

- Creating a private room with `is_public=true` is rejected with
  `409 private_room_cannot_be_public`.
- `PATCH /chat/api/chats/{id}` rejects `is_public=true` when the room has a
  room code or `is_private=1`.
- `configure_private_room()` clears `is_public` and the public username when a
  chat becomes a private room, repairing legacy inconsistent rows.
- `_can_access_chat()` treats a legacy public+coded row as private: the public
  flag alone is no longer enough.
- `_row_to_chat()` normalizes the API view: a private/coded row is never
  advertised as public, even if a legacy DB row still has `is_public=1`.
- The SPA hides the public checkbox/username for private rooms and coded rooms,
  and the settings handler no longer assumes those controls exist.
- The join-request block is shown only to owners/platform staff or members with
  `manage_invites`, so admins without that right no longer see a false “0”.

## P1-2 — auto-moderation covers polls

- Poll creation now runs the question and every option through
  `AutoModerationService.check_message()`.
- The helper accepts `extra_text`; ordinary message/edit/forward calls are
  unchanged.
- A poll report is filed into the normal moderation queue, with the poll
  message id as the report target.

## P2-3 — one quota count

- `AccountService.get_limits()` excludes `chat_type='dm'`, matching
  `ChatLimitsService`.
- Moderators now get the same unlimited-custom-chat result as admins.
- The profile no longer shows the impossible “6 of 5” state.

## P2-4 — pending request counters are manager-only

- `get_chat_view()` returns `pending_requests: 0` unless the requester has
  `manage_invites`. Public readers no longer see moderation queue size.
- The public member list remains visible for public chats by product decision;
  only the internal counter is restricted.

## P3 fixes

- Duplicate poll options (case-insensitive) are rejected with
  `422 duplicate_poll_option`.
- Leaving the common chat returns `409 common_chat_protected` instead of a
  silent no-op; removing members from the common chat is protected too.
- Deleting a pinned message clears `chats.pinned_message_id`.

## Verification

- New suite `tests/server/test_business_logic_p123_2026_11_10.py` — **28/28**.
- Existing suites: P0 32/32, 09d 29/29, 09c 38/38, 09b 20/20, access 38/38,
  admin boundary 26/26, updates 10/10 — **220/220** total in this run.
- UI affected areas: admin 13/13, ui_test 24/24, profile 33/33, p2 24/24,
  automod 23/23, groups 34/34 — **151/151**.
- `node --check` for `devices.js`/`rfid.js` remains clean from the P0 pass.

Remaining review items are product-model decisions (roles, privacy model,
notifications, voice, applications) or lower-priority UX work, not regressions
from this pass.
