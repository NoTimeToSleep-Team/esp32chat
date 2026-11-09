# Security fixes — 2026-11-09 (third pentest)

Fixes for `C:\Users\Пользователь\esp32chat-pentest-2026-11-09\REPORT.md`.

The report was taken against commit `f26fe19`. Findings F-04 (closed-mode
registration), F-05/F-12 (block and slow-mode bypass via forward/group
creation) and F-08 (edit/delete after kick) were already closed by commits
`5f0d154` and `7b427e7`; their regressions remain green below.

## Group-admin permission bypass (F-01)

- Every management operation now checks the matching permission flag:
  - `change_info`: chat avatar set/clear;
  - `manage_invites`: create/list/revoke invites and list/decide join
    requests;
  - `restrict_members`: remove member, change role, change admin permissions.
- `set_member_permissions` rejects self-changes with
  `403 self_permission_change`; only the owner or a platform
  administrator/moderator may change another admin's permissions.
- Only the owner or a platform administrator/moderator may appoint an
  `admin`; a restricted group admin cannot promote a collaborator into a full
  admin account by granting the default permission set.
- Demoting or removing an admin deletes the invites that admin created, so a
  restricted admin cannot leave a persistent invite backdoor.

## Debug-trace log flood (F-02)

- `X-Debug-Trace` is written only for an authenticated web session. The
  middleware validates `X-Session-Token` (or the legacy `session_token`
  fallback) before writing.
- 404 responses and `/health*`, `/static/*`, `/docs*`, `/redoc`,
  `/openapi.json` are never logged by the trace middleware.
- Debug writes are limited to 120/minute per IP, executed in a worker thread,
  and the log is still pruned on startup (7 days / 50,000 rows).

## Poll and message-size DoS (F-03)

- Poll questions and each option are limited to 300 characters; options JSON is
  limited to 16 KiB. Oversized legacy rows are truncated on read.
- Message pages are capped at 200 messages (API and service).
- New messages, forwards and polls are rejected with `507 storage_full` when
  the database filesystem has less than `LCS_MIN_DB_FREE_MB` free
  (default 50 MiB).

## Invite race (F-07)

- Joining an invite now inserts membership first and claims a use with an
  atomic conditional `UPDATE ... WHERE uses < max_uses AND not expired`.
- If the claim fails, the transaction is rolled back and the join returns
  `410 invite_exhausted` / `invite_expired`; `max_uses` cannot be exceeded by
  concurrent requests.
- Join-request approval uses the same expiry-aware conditional update.

## Device-id evasion (F-06)

- A `device_id` can create only one account, including web registrations.
- Web sessions are bound to the account's first registration device, so
  changing the local `device_id` in `localStorage` does not detach the session
  from the canonical device.
- Standard login/session checks still consult the device blacklist on every
  authenticated request.
- Residual limitation: a browser-supplied device id is not hardware
  attestation. A user with a fresh browser profile can still present a new id;
  hardware identity assurance remains the pairing flow (`/auth/device-session`)
  used by ESP32 clients.

## Enumeration minimization (F-13)

- Login search returns `user_id` and `login`; platform roles are only exposed
  to admin/moderator viewers.
- Foreign profiles return a generic `user` role and `active` status instead of
  the target's real platform role/status.
- Member statuses are only returned to the member themselves or platform
  moderators.

## Verification

- New local integration suite:
  `tests/server/test_security_fixes_2026_11_09c.py` — **38 passed, 0 failed**
  (permission matrix, persistent invites, invite race, poll limits, debug
  trace, device binding, enumeration).
- Previous regressions: `test_security_fixes_2026_11_09b.py` — **20 passed,
  0 failed**; `test_chat_access_regressions.py` — **38 passed, 0 failed**.

## Remaining operator actions

- F-09: keep `profile=test` only on the isolated stand; use `prod` (or close
  `/docs` at the network layer) for any wider deployment.
- F-10: the old admin password remains in public git history. Rewriting a
  published `main` requires a coordinated force-push and is intentionally not
  done as part of this code change; the live password was already rotated.
- F-11: TLS termination and replacing query-string media tokens with
  short-lived signed URLs or header-based fetches remain deployment/UI work.
- Review the board for test accounts/chats created by the pentester and remove
  them with the admin panel.
