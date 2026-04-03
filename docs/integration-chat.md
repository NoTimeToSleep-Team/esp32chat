# Chat Integration

This document tracks software-level e2e integration for chat delivery parity between web and device flows.

## Scope (`v0.15.02`)

- send chat message from a hardware-style (`client_kind=device`) flow;
- receive the same message in web realtime channel (`/realtime/chat/{chat_id}`);
- map the same message to firmware protocol event shape (`chat.message.event`);
- verify that web event and device event carry the same semantic data.

## Integration Contract Focus

- web realtime event type: `chat.message`;
- firmware protocol event type: `chat.message.event`;
- parity fields: `chat_id`, `author_user_id`, text (`body_text` <-> `text`), `created_at_ms`.

Server-side mapping helper lives in `server/app/realtime/events.py`:

- `chat_message_payload(...)` for web payload reuse;
- `chat_protocol_event_payload(...)` for protocol-compatible payload mapping.

## Local Verification

Run from project root:

```bash
python -m firmware.integration.verify_chat_e2e
```

Verification asserts:

- required HTTP + websocket routes exist for integration path;
- one message sent via device flow is received in web realtime stream;
- both web and device history endpoints include the same sent message;
- mapped protocol payload validates via firmware protocol envelope (`chat.message.event`);
- parity fields match between web event and device protocol payload.

## Hardware Note

This check is software e2e against FastAPI `TestClient` + in-process websocket.
Real network quality and on-device runtime behavior remain a separate hardware validation step.
