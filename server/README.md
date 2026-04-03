# Server Zone

This directory contains the Raspberry Pi server side of the system.

## Current State

- FastAPI foundation is initialized in `app/main.py`.
- Python project metadata is defined in `pyproject.toml`.
- Environment configuration and startup validation are defined in `app/config.py`.
- Config examples are provided in `config/*.env.example`.
- Health endpoints are available in `app/api/health.py`.
- Base application logging is configured in `app/logging.py`.
- Data layer bootstrap is implemented in `app/db/*` with SQL migrations in `migrations/*`.
- User domain model for roles and restrictions is defined in `app/models/user.py`.
- Auth service and API are implemented in `app/services/auth.py` and `app/api/auth.py`.
- Closed-mode application flow is implemented in `app/models/application.py`, `app/services/applications.py`, `app/api/applications.py`.
- Open-mode registration and mode-switch are implemented in `app/services/registration.py`, `app/services/mode.py`, `app/api/mode.py`.
- Chat core domain is implemented in `app/models/chat.py` and `app/services/chat.py`.
- Realtime chat transport is implemented in `app/realtime/*` and `app/api/realtime.py`.
- Chat web UI is implemented in `app/templates/chat/*`, `app/static/chat/*`, `app/api/chat.py`.
- Private rooms and chat limits are implemented in `app/services/chat_limits.py`, `app/api/chat_private.py`.
- Blog domain and API are implemented in `app/models/blog.py`, `app/services/blog.py`, `app/api/blog.py`, `app/templates/blog/*`, `app/static/blog/*`.
- Support domain and API are implemented in `app/models/support.py`, `app/services/support.py`, `app/api/support.py`, `app/templates/support/*`, `app/static/support/*`.
- Account domain and API are implemented in `app/models/account.py`, `app/services/account.py`, `app/api/account.py`, `app/templates/account/*`, `app/static/account/*`.
- Devices catalog domain and API are implemented in `app/models/device_catalog.py`, `app/services/devices.py`, `app/api/devices.py`, `app/templates/devices/*`, `app/static/devices/*`.
- Admin users domain and API are implemented in `app/models/admin_users.py`, `app/services/admin_users.py`, `app/api/admin/users.py`, `app/templates/admin/users/*`, `app/static/admin/users/*`.
- Admin content and mode APIs are implemented in `app/api/admin/content.py`, `app/api/admin/mode.py`, `app/templates/admin/content/*`, `app/templates/admin/mode/*`, `app/static/admin/content/*`, `app/static/admin/mode/*`.
- RFID/NFC domain and API are implemented in `app/models/rfid.py`, `app/services/rfid.py`, `app/api/rfid.py`, `app/templates/rfid/*`, `app/static/rfid/*`.
- Security baseline is implemented in `app/security/*`, middleware in `app/main.py`, and login guard in `app/api/auth.py`.
- Ops-safety services and API are implemented in `app/services/backup.py`, `app/services/incidents.py`, `app/services/shutdown.py`, `app/api/ops.py`.
- Raspberry Pi deploy package is prepared in `systemd/*`, `config/nginx/*`, `scripts/install_pi.*`, `docs/deploy-pi.md`.

## Planned Scope

- backend application and APIs;
- web portal and admin interfaces;
- auth, roles, and access policies;
- chat, blog, support, and account flows;
- defensive security, logs, backups, and safe shutdown.

## Planned MVP Stack

- Python backend (FastAPI or equivalent);
- SQLite for MVP data layer;
- Nginx for local portal and reverse proxy;
- WebSocket or SSE for realtime messaging;
- systemd for service lifecycle.

## Notes

- Raspberry Pi 5 remains the single main server node.
- Guest access is allowed only for web mode.
- Hardware clients are not allowed to use guest mode.

## Quick Start (foundation)

```bash
python -m pip install -e .
uvicorn app.main:app --reload
```

## Configuration

- Default profile: `LCS_PROFILE=dev`.
- Production profile must set explicit `LCS_ALLOWED_ORIGINS` and strong `LCS_SESSION_SECRET`.
- Invalid configuration fails app startup at import time.

## Health and Logging

- Health: `GET /health`
- Readiness: `GET /health/ready`
- Startup and shutdown events are logged through application logger.

## Data Layer

- On startup, app initializes storage layout under `LCS_STORAGE_ROOT`.
- SQL migrations from `migrations/*.sql` are applied once and tracked in `schema_migrations`.
- Baseline SQLite schema is created by `migrations/0001_initial.sql`.

## Auth Endpoints

- `POST /auth/login`
- `POST /auth/logout`
- `GET /auth/session/{session_token}`
- `POST /auth/register`
- `POST /auth/guest`

Registration constraints:

- open mode only;
- one phone per account;
- one device id per account;
- guest access only for web clients.

## Closed Mode Applications

- `POST /applications` - submit application when mode is `closed`.
- `GET /applications` - admin queue view (`X-Session-Token` required).
- `POST /applications/{application_id}/status` - admin status update.

## Mode Endpoints

- `GET /mode`
- `POST /mode` - admin mode switch (`X-Session-Token` required).

## Realtime

- WebSocket: `GET /realtime/chat/{chat_id}?session_token=<token>`
- Supported incoming events: `ping`, `chat.history`, `chat.send`
- Outgoing events: `realtime.connected`, `chat.message`, `chat.history`, `chat.ack`, `error`

## Chat Web UI

- Page: `GET /chat`
- Chat list: `GET /chat/api/chats`
- Message history: `GET /chat/api/chats/{chat_id}/messages`
- Send message: `POST /chat/api/chats/{chat_id}/messages`

## Private Rooms and Limits

- Create private room: `POST /chat/api/private`
- Join private room: `POST /chat/api/private/{chat_id}/join`
- Room members: `GET /chat/api/private/{chat_id}/members`
- Room config update: `POST /chat/api/private/{chat_id}/config`

Rules:

- user: up to 5 custom chats;
- admin: no custom chat limit;
- guest cannot create chats;
- private room supports optional 4-digit room code;
- admin can access all chats.

## Blog

- Page: `GET /blog`
- Posts list: `GET /blog/api/posts`
- Post details: `GET /blog/api/posts/{post_id}`
- Publish post (admin): `POST /blog/api/posts`

Rules:

- only admin can publish posts;
- any active authenticated web session can read the feed.

## Support

- Page: `GET /support`
- Create ticket: `POST /support/api/tickets`
- List tickets: `GET /support/api/tickets`
- Ticket messages: `GET /support/api/tickets/{ticket_id}/messages`
- Send message: `POST /support/api/tickets/{ticket_id}/messages`
- Update status (admin): `POST /support/api/tickets/{ticket_id}/status`

Rules:

- support is available for authenticated non-guest accounts;
- user sees only own tickets, admin sees full queue;
- status is changed by admin, and admin reply moves `open` ticket to `in_progress`.

## Account

- Page: `GET /account`
- Read profile: `GET /account/api/profile`
- Update profile: `POST /account/api/profile`
- Upload avatar: `POST /account/api/avatar`
- Read own avatar file: `GET /account/api/profile/avatar`
- Read limits: `GET /account/api/limits`

Rules:

- avatar uses `data/avatars` storage and supports png/jpeg/webp up to 2MB;
- guest can read profile and limits, but cannot change profile or avatar;
- profile updates do not invalidate active session token.

## Devices

- Page: `GET /devices`
- List catalog: `GET /devices/api/catalog`
- Read profile: `GET /devices/api/catalog/{device_id}`
- Publish profile (admin): `POST /devices/api/catalog`
- Set "I have this device" flag: `POST /devices/api/catalog/{device_id}/ownership`

Rules:

- profile publishing is admin-only;
- non-admin users see published profiles only;
- ownership flag is available for authenticated non-guest accounts.

## Admin Users

- Page: `GET /admin/users/panel`
- Users list: `GET /admin/users`
- User details: `GET /admin/users/{user_id}`
- Ban user: `POST /admin/users/{user_id}/ban`
- Unban/restore user: `POST /admin/users/{user_id}/unban`
- Temporary block: `POST /admin/users/{user_id}/temporary-block`
- Blacklist user device: `POST /admin/users/{user_id}/blacklist-device`
- Unblacklist user device: `POST /admin/users/{user_id}/unblacklist-device`
- Delete user: `DELETE /admin/users/{user_id}`

Rules:

- all endpoints are admin-only;
- admin cannot ban/block/delete own account;
- registration blocks blacklisted devices;
- expired temporary block is lifted automatically on next auth/session check.

## Admin Content and Mode

- Content panel page: `GET /admin/content/panel`
- Applications queue: `GET /admin/content/applications`
- Application review: `POST /admin/content/applications/{application_id}/status`
- Support queue: `GET /admin/content/support/tickets`
- Support messages: `GET /admin/content/support/tickets/{ticket_id}/messages`
- Support reply: `POST /admin/content/support/tickets/{ticket_id}/reply`
- Support status update: `POST /admin/content/support/tickets/{ticket_id}/status`
- Blog list/publish: `GET /admin/content/blog/posts`, `POST /admin/content/blog/posts`
- Mode panel page: `GET /admin/mode/panel`
- Mode state/set: `GET /admin/mode/state`, `POST /admin/mode/set`

Rules:

- admin-only for all `/admin/content/*` and `/admin/mode/*` endpoints;
- mode set requires hold confirmation (`hold_seconds >= 5`);
- admin workflows cover applications, support queue, blog publish and mode toggle.

## RFID / NFC

- Page: `GET /rfid`
- Card list: `GET /rfid/api/cards`
- Enroll/overwrite card: `POST /rfid/api/cards`
- Toggle card active flag: `POST /rfid/api/cards/{card_id}/active`
- Delete card: `DELETE /rfid/api/cards/{card_id}`
- Events list: `GET /rfid/api/events`
- Verify card UID: `POST /rfid/api/verify`
- Switch mode by card: `POST /rfid/api/mode/switch-by-card`

Rules:

- card UID is normalized and stored as HMAC hash with masked UID for display;
- card enrollment/removal/list/events are admin-only;
- mode switch by card can unlock or set mode without password session, based on active registered card;
- implementation is practical local RFID access control and does not claim banking-grade cryptography.

## Security Baseline

- Global request rate limiting is enabled by middleware (IP-based, configurable via env).
- Auth routes use stricter per-IP request budget than regular API routes.
- Login brute-force guard tracks failed attempts and temporarily blocks abusive IPs.
- Security-relevant events are written into `audit_log` (`security.login_*`, `security.rate_limit_block`).

Tuning env vars:

- `LCS_RATE_LIMIT_WINDOW_MS`, `LCS_RATE_LIMIT_MAX_REQUESTS`
- `LCS_AUTH_RATE_LIMIT_WINDOW_MS`, `LCS_AUTH_RATE_LIMIT_MAX_REQUESTS`
- `LCS_BRUTEFORCE_WINDOW_MS`, `LCS_BRUTEFORCE_LOGIN_ATTEMPT_LIMIT`
- `LCS_BRUTEFORCE_IP_ATTEMPT_LIMIT`, `LCS_BRUTEFORCE_BLOCK_MS`

## Ops Safety

- Runtime state: `GET /ops/api/state`, `POST /ops/api/degraded-mode`
- Backups: `GET /ops/api/backups`, `POST /ops/api/backups`, `POST /ops/api/backups/dry-run`
- Restore dry-run: `POST /ops/api/backups/restore/dry-run`
- Incidents: `GET /ops/api/incidents`, `POST /ops/api/incidents`, `POST /ops/api/incidents/{incident_id}/resolve`
- Shutdown dry-run: `POST /ops/api/shutdown/dry-run`, `GET /ops/api/shutdown/runs`

Rules:

- all ops endpoints are admin-only;
- backup flow stores history in SQLite and uses `data/backups` for snapshot files;
- restore endpoint is dry-run only at this stage (no destructive overwrite);
- shutdown orchestration is dry-run only and records planned sequence steps;
- degraded mode state is persisted and can be toggled explicitly by admin.

## Deploy (Pi OS)

- systemd unit: `systemd/local-chat-server.service`
- nginx site: `config/nginx/local-chat-server.conf`
- installer: `scripts/install_pi.sh`
- Windows SSH helper: `scripts/install_pi.ps1`
- deployment guide: `docs/deploy-pi.md`
