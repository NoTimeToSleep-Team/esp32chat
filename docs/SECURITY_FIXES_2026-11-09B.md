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
- The systemd unit binds the proxy to `192.168.4.1` (AP interface) and runs as
  the unprivileged `localchat` user. It also has `MemoryMax`, `TasksMax`,
  `LimitNOFILE`, an empty capability set and the usual systemd sandboxing.
- Live check: `192.168.4.1:3128` is the only listener; an internet-off HTTP
  request returns the captive-portal redirect.

## SSH and local credential exposure (C1/C2)

- Password SSH is disabled by
  `/etc/ssh/sshd_config.d/00-local-chat-hardening.conf`; key-only auth is
  enforced with `AuthenticationMethods publickey`, and root login is limited to
  keys.
- A dedicated Ed25519 key is installed for `gamecat`; the deployment helpers
  `lc-ssh.py` / `lc-scp.py` no longer contain a password.
- `lc-askpass.cmd`, `lc-close-open.sh`, `lc-usb-cleanup.sh`,
  `TEST_CREDENTIALS.txt` and the password screenshot were removed locally.
- The cached GitHub credential in Windows Credential Manager was deleted.

## Verification

- Local integration: `20 passed, 0 failed` for H1, L1, M2, M3, H2, L2, guest DM
  policy and proxy SSRF helpers.
- Existing access regressions: `38 passed, 0 failed`.
- Live board: server/proxy active, `/health` 200, deployed file hashes matched,
  proxy listening only on `192.168.4.1:3128`, Host-header redirect is relative,
  and password SSH authentication is rejected.

## Remaining operator actions

- Revoke the GitHub PAT that was found in `lc-askpass.cmd`; issue a
  fine-grained replacement with the minimum scopes and short TTL, then sign in
  again (the cached credential was removed).
- Rotate the admin web password and review GitHub audit logs / Actions secrets.
- Rotate the `gamecat` password from the physical console. Remote password login
  is already disabled; the password remains relevant to local sudo.
- Review SSH auth logs and authorized keys on the board.
- The `test` profile still exposes `/docs` and `/openapi.json`; keep this only on
  the isolated test stand, not in production.
