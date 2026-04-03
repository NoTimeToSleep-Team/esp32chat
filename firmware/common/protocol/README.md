# Common Protocol Module

Shared protocol code for `v0.07.02` based on `contracts/protocol.md` and `contracts/messages/*.json`.

## Files

- `constants.py` - protocol version, endpoint/message/error enums.
- `errors.py` - protocol-specific error classes.
- `models.py` - typed envelope and endpoint models.
- `schema.py` - payload validation rules per `message_type`.
- `idempotency.py` - idempotency key formatting and validation.
- `codec.py` - JSON encode/decode and envelope validation.
- `verify_contract_samples.py` - sample coverage check for contract messages.

## Coverage

Supported message types:

- `device.register.request`
- `device.register.response`
- `device.heartbeat`
- `telemetry.snapshot`
- `auth.login.request`
- `auth.login.response`
- `chat.send.request`
- `chat.send.response`
- `chat.message.event`
- `sync.push.request`
- `sync.push.response`
- `sync.pull.request`
- `sync.pull.response`
- `sync.ack`
- `error.response`

## Local Verification

Run from project root:

```bash
python -m firmware.common.protocol.verify_contract_samples
```

Expected output includes:

- `CONTRACT_SAMPLES_VALIDATED <count>`
- `CONTRACT_SAMPLES_ROUNDTRIP <count>`
