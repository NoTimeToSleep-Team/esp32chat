# Common Queue Module

Implemented for `v0.07.03` as a shared queue baseline.

## Files

- `states.py` - event states (`pending`, `sent`, `acked`, `duplicate`, `rejected`).
- `models.py` - queue event record model with retry/error metadata.
- `hashing.py` - canonical payload hash for replay safety.
- `memory.py` - local in-memory queue with idempotent enqueue and state transitions.

## Notes

- Queue implements idempotent enqueue by `idempotency_key` + payload hash.
- Retry readiness is delegated to transport retry policy (`RetryGate`).
- Durable persistence is intentionally deferred to device-specific stages.
