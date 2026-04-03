# Ops Integration

This document tracks software-level e2e integration for the remaining mandatory stage-15 operational flows:

- blog;
- support;
- admin operations.

## Scope (`v0.15.03`)

- admin publishes a blog post;
- device flow reads the published blog post;
- device flow creates a support ticket;
- admin reviews ticket queue, replies, and updates ticket status;
- device flow reads support thread and resolved status.

## Server API Endpoints Covered

- `POST /admin/content/blog/posts`
- `GET /blog/api/posts`
- `GET /blog/api/posts/{post_id}`
- `POST /support/api/tickets`
- `GET /support/api/tickets`
- `GET /support/api/tickets/{ticket_id}/messages`
- `GET /admin/content/support/tickets`
- `POST /admin/content/support/tickets/{ticket_id}/reply`
- `POST /admin/content/support/tickets/{ticket_id}/status`

## Local Verification

Run from project root:

```bash
python -m firmware.integration.verify_ops_e2e
```

Verification asserts:

- integration command map matches available server routes;
- admin blog publication is visible in device blog read flow;
- support ticket created from device flow appears in admin queue;
- admin reply and status update are visible in device support read flow.

## Hardware Note

This check is software e2e via FastAPI `TestClient`.
Real network/device runtime checks remain a separate hardware validation step.
