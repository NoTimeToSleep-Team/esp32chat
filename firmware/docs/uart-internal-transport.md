# Internal UART Transport (Heavy Payload Path)

This document defines the baseline UART framing used for internal heavy-data transfer where I2C is not suitable.

## Scope

- Keep I2C for short service messages only (status, heartbeat, tiny telemetry, control signals).
- Use UART/USB serial framing for larger buffered payloads.
- Keep retry/ACK behavior explicit and deterministic.

## Frame Format (v1)

Byte layout:

1. `start` (1 byte): `0x7E`
2. `version` (1 byte): `1`
3. `flags` (1 byte):
   - `0x01` = ACK required
   - `0x02` = ACK frame
4. `sequence` (2 bytes, big-endian)
5. `payload_len` (2 bytes, big-endian)
6. `payload` (`payload_len` bytes)
7. `crc32` (4 bytes, big-endian), calculated over `version..payload`

Constraints:

- max payload size: `4096` bytes;
- sequence range: `0..65535`;
- parser must recover from stream corruption by re-scanning start byte and validating CRC.

## Python Reference

Implementation:

- `firmware/common/transport/uart_framing.py`
- `firmware/common/transport/uart_adapter.py`

Verifier:

- `firmware/common/transport/verify_uart_framing.py`
- `firmware/common/transport/verify_uart_transport_adapter.py`
- `firmware/common/transport/verify_uart_sync_retry.py`

Run:

```bash
python -m firmware.common.transport.verify_uart_framing
python -m firmware.common.transport.verify_uart_transport_adapter
python -m firmware.common.transport.verify_uart_sync_retry
```

Verifier covers:

- frame build/parse roundtrip;
- chunked stream parsing;
- CRC mismatch rejection.
- envelope-over-UART adapter send/receive with ACK guard behavior.
- UART-backed sync retry flow with sequence rollover (`65535 -> 0`).
