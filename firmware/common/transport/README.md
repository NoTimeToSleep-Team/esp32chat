# Common Transport Module

Implemented for `v0.07.03` as a shared runtime baseline.

## Files

- `errors.py` - transport error model (`TransportIOError`, protocol-level wrappers).
- `retry.py` - exponential backoff retry policy (`1s..30s`, then fixed 30s).
- `adapters.py` - transport adapter protocol and in-memory adapter for validation.
- `sync_push.py` - queue-aware `sync.push` sender with ACK/duplicate/reject handling.
- `reconnect.py` - reconnect orchestration: session check -> push -> pull -> ack.
- `verify_transport_queue.py` - end-to-end verification scenario for retry/idempotency.

## Verification

Run from project root:

```bash
python -m firmware.common.transport.verify_transport_queue
```
