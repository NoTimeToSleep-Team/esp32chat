# Security fixes — 2026-11-09

Fixes for the 2026-11-08 pentest report. The report IDs match the sections below.

## WebSocket sessions (H-01)

- A live socket is bound to its session id, expiry and device id.
- Logout, ban, temporary block, password reset, user deletion, device
  unpair/reset and device blacklist close every affected WebSocket with code
  `4401`.
- Every WebSocket command revalidates the session; expired sessions are also
  swept before a broadcast.
- `chat.send` / `chat.history` no longer work after logout or revocation.

## Direct chats and guests (H-02, M-03, L-03)

- Guests may create a DM to a regular user and write to them.
- Guests still cannot create custom group chats.
- DMs are immutable two-party rooms: no adding members, invite links, public
  publishing, username, role changes, ownership transfer or unilateral delete.
- A participant may only leave a DM; the other participant keeps their copy.
- Legacy published DMs are readable only by their two members; a participant can
  revoke publication, but nobody can publish a DM through the API.
- DM lookup requires `chat_type='dm'` and exactly two members.
- DMs do not count toward the five-custom-chat limit.

## Realtime resource limits (H-03)

- Global WebSocket cap: 200.
- Per-user cap: 5; per-IP cap: 10.
- WebSocket handshakes go through the existing per-IP rate limiter.
- Stalled clients are closed with a bounded timeout so they cannot hold an
  admin request open.

## Debug trace writes (H-04)

- `X-Debug-Trace` SQLite middleware is disabled by default and can only be
  enabled with `LCS_DEBUG_TRACE_ENABLED=true` for development.
- Health, static, docs and OpenAPI requests are never traced.
- Debug rows are pruned at startup (7 days / 50,000 rows).

## Hidden reply previews (M-01)

- Broadcast events contain `reply_to_message_id` but not `reply_to_text` or
  `reply_to_login`; the per-viewer HTTP history remains the only source of the
  preview after readability filtering.

## Blocks and slow mode (M-02, L-02)

- Block checks apply to send, forward, poll creation, editing, reactions and
  poll voting in DMs.
- A DM remains blocked even if a legacy room has more than two members.
- Slow mode is enforced on forwards and edits, not only on new messages.

## Device blacklist (M-04)

- Web login requires a stable `device_id`; the SPA, static login and admin panel
  persist one in local storage.
- The first registration device remains the account identity and is checked on
  every login/session validation even when a client presents a new id.
- Blacklisting revokes all sessions of the target user and closes their
  WebSockets.

## Guest public-chat access (L-04)

- Guests can discover, join and write in public custom groups.
- Guests can read the common chat but cannot post there.
- Public custom chat search and message search include guest accounts.
- DMs remain membership-only and are never returned by public search.

## Verification

Local integration runs against a temporary SQLite database and uvicorn:

- guest DM + public custom chat policy: `14 passed, 0 failed`;
- existing F8–F12 access regressions: `38 passed, 0 failed`;
- earlier security suite (before the guest-DM policy change):
  `29 passed, 0 failed`.
