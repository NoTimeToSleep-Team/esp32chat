# Security hardening — 2026-11-01

Remediation pass for the read-only security report. The live admin password was
intentionally not changed, as requested by the owner.

## Fixed

- Debug/access logs redact `session_token`, `token`, `password`, `secret` and
  bearer values; old debug events are purged by `scripts/security_lockdown.py`.
- `/debug/api/events` is admin-only; `/debug/api/client-event` requires a valid
  session.
- Session lifetime reduced from 30 days to 24 hours; all existing sessions are
  revoked during the lockdown run.
- `X-Forwarded-For` is ignored for rate limits, brute-force keys and audit
  identities. Uvicorn is started with `--no-proxy-headers`.
- Chat membership changes require the `invite_users` permission; self-insertion
  cannot bypass invite/room-code/public-chat consent. Roles are not accepted by
  the add-member endpoint; role changes go through the separate role endpoint.
- New members cannot read history when `history_visible` is disabled; non-members
  are rejected instead of receiving the archive.
- Invite `max_uses` is enforced on the approval path as well as direct joins.
- New private-room codes are 6 digits; 4-digit codes remain accepted only for
  joining legacy rooms.
- Chat titles reject markup/control characters; quote-safe escaping is used in
  the SPA, admin panel and legacy `/chat` page. The legacy chat page's broken
  JavaScript was repaired.
- Anonymous endpoints were closed or protected: `/sync/api/events/*`,
  `/api/m5tab/*`, `/ops/system-health`, `/api/capabilities`,
  `/devices/api/edge/capabilities`, avatar retrieval and device-status lookup.
- Device pairing/unpairing enforces ownership; pairing status never discloses
  the owner id.
- `?token=` auto-login and `/auth/session/{token}` were removed; the session
  endpoint now requires `X-Session-Token`.
- JSON API clients use `X-Session-Token` and strip the token from request URLs.
  The backend keeps query-token compatibility for media/legacy clients and
  redacts it from logs.
- Security headers added: CSP, `X-Content-Type-Options`, `Referrer-Policy`,
  `X-Frame-Options`, `Permissions-Policy`; API responses are `no-store`.
- Production API docs/OpenAPI are disabled.
- `verify_password()` no longer accepts plaintext values from the hash column.
- Test credentials were removed from the current tree; UI/Python suites now
  require `LC_ADMIN_PASSWORD`.

## Residual / requires a separate decision

- **Admin password**: not changed. The old value exists in public git history,
  so rotating it (or restricting admin login by network/device) is still the
  only way to fully close the original credential leak.
- **Git history**: the old credential remains in historical commits. Removing
  it requires an intentional history rewrite/force-push and credential rotation.
- **Query-token compatibility**: media and legacy URLs may still carry
  `session_token`; logs are redacted and `Referrer-Policy: no-referrer` is set,
  but a full cookie/header-only migration would remove the remaining exposure.
- **CSP**: inline scripts/handlers are still allowed because the UI is built
  around them; the confirmed XSS sinks are fixed, but a nonce/external-script
  migration remains future work.
- **RFID**: module is disabled; its unauthenticated hardware callbacks were not
  redesigned in this pass.
- **Dependency CVEs**: no lockfile/vulnerability database run was performed.
- **Mass registration**: existing per-IP auth rate limits remain; open-mode
  registration policy still needs a product decision.
