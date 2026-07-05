# Firmware Common

Shared firmware modules that are reused by multiple device targets.

## Structure

- `protocol/` - packet types, serializers, versioning, and protocol errors.
- `transport/` - transport adapters, retry policy, ACK handling.
- `queue/` - local event queue and replay helpers.
- `platform/` - platform abstraction points for ESP32/M5/Flipper families.
- `messages/` - canonical message schemas and mapping notes.

Current status:

- `v0.07.02`: protocol constants/codec/validation is implemented in `protocol/*`.
- `v0.07.03`: transport and queue runtime baseline is implemented in `transport/*` and `queue/*`.
