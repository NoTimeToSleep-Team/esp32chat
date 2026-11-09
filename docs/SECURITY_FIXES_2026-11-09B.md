# Security fixes — 2026-11-09 (second pentest)

Fixes for `esp32chat-pentest-report-2026-11-09.md`.

## Closed-mode registration (H1)

- `RegistrationService.register_user()` now requires `access_mode=open` unless
  the caller is the local CLI installer (`allow_closed_mode=True`).
- `POST /auth/register` in closed mode returns `403 registration_closed`; the
  application flow remains the only public onboarding path.

## WebSocket message limits (H2)

- `chat.send` now enforces the same 4000-character message limit as the REST
  endpoint, plus a 128-character `client_message_id` limit. The check lives in
  `ChatService.send_message()` so every caller is covered.
- Realtime events are limited to 30/minute per user and 60/minute per IP.
- WebSocket frame size remains capped at 64 KiB.

## Guest direct messages (M1)

- Guest DMs remain intentionally allowed by product policy, but new guest DM
  creation is limited to 5 per 10 minutes.
- Guest messages are covered by the realtime/user and HTTP limits above.
- Guests still cannot create groups or receive DMs as a target.

## Block bypass (M2)

- `create_custom_chat()` rejects any member who has a block relationship with
  the creator.
- `add_member()` rejects the target if any existing member has a block
  relationship with that target.

## Host-header redirect (M3)

- Trailing-slash 307/308 redirects are rewritten to origin-relative
  `Location` values, so a forged `Host` cannot create an open redirect.

## Device sessions (L1)

- Password login with `client_kind=device` is rejected with
  `device_session_required`.
- Device sessions must use `/auth/device-session` with the pairing challenge
  and proof.

## Edit/delete after kick (L2)

- `edit_message()` and `delete_message()` require the actor to still be a
  member of the chat (platform admins/moderators keep moderation access).

## Static login device id (B1)

- The static login form already persists and sends a stable `device_id`; the
  updated template is included in the deployment.

## Internet proxy (C3/H3)

- The transparent proxy only connects to globally routable addresses and only
  ports 80/443. Loopback, RFC1918, link-local, multicast and reserved ranges are
  rejected for both HTTP and CONNECT.
- DNS is resolved before connect and all returned addresses must be public;
  the proxy connects to the validated address rather than re-resolving.
- Request headers are bounded, client/remote reads have timeouts, connections
  are capped globally and per IP, and a bounded thread pool replaces
  thread-per-connection.
- The systemd unit binds the proxy to `192.168.4.1` (AP interface), sets
  resource limits and drops capabilities.

## Verification

- Local integration: `20 passed, 0 failed` for H1, L1, M2, M3, H2, L2, guest DM
  policy and proxy SSRF helpers.
- Existing access regressions: `38 passed, 0 failed`.
- Host-level credential actions are tracked separately below.

## Remaining operator actions

- Revoke the GitHub PAT that was found in `lc-askpass.cmd`; issue a
  fine-grained replacement with the minimum scopes and short TTL.
- Rotate the admin web password and review GitHub audit logs / Actions secrets.
- Review SSH auth logs and authorized keys on the board after the key-only
  deployment.
