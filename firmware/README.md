# Firmware Zone

This directory contains firmware workspace artifacts for internal service nodes and external client devices.

## Current Stage

- Stage 15 Integration is in progress (`v0.15.02` active).
- Shared protocol code is implemented under `common/protocol/`.
- Shared transport and queue baseline is implemented under `common/transport/` and `common/queue/`.
- Internal UART frame baseline for heavy intra-block payload path is implemented under `common/transport/uart_framing.py`.
- UART envelope adapter baseline is implemented under `common/transport/uart_adapter.py`.
- ESP32-S3 service controller MVP is implemented under `devices/esp32_service/`.
- ESP32 service queue sync path now supports transport selection baseline (`inmemory` / UART framed) under `devices/esp32_service/sync_transport.py`.
- M5Stamp S3 helper-node MVP is implemented under `devices/m5stamp/`.
- Atom S3 status/alert MVP is implemented under `devices/atom_s3/`.
- M5Tab shell/info, admin-users and admin-ops MVP is implemented under `devices/m5tab/`.
- M5Cardputer built-in console shell/login + chat + blog/service MVP is implemented under `devices/m5cardputer_console/`.
- M5Cardputer external client profile split/shared-base + client MVP is implemented under `devices/m5cardputer_client/`.
- M5StickC Plus 2 compact shell/login + client MVP is implemented under `devices/m5stickc_plus2/`.
- T-Embed CC1101 shell/login + text-first client MVP is implemented under `devices/t_embed_cc1101/`.
- Flipper Zero shell/capability-detection + limited client MVP is implemented under `devices/flipper_zero/`.
- Native Arduino `.ino` runtime entrypoints are now present for all ESP32/M5 targets under `devices/*/*.ino`.
- Native Flipper `.fap` C runtime entrypoint is now present under `devices/flipper_zero/fap/`.
- Native client/admin write actions are opt-in via compile-time macros (disabled by default).
- Device-specific Arduino preset headers are tracked under `arduino/presets/*_preset.h`.
- Profile metadata now explicitly tracks `host_harness_entries` for Python-side verification files.
- Runtime/harness mapping is documented in `docs/native-runtime-map.md`.
- Python harness policy is documented in `docs/python-harness-policy.md`.
- Device registration/telemetry e2e baseline is verified via `devices/esp32_service/verify_registration_e2e.py`.
- Chat web+device e2e parity is verified via `integration/verify_chat_e2e.py`.
- Blog/support/admin ops e2e is verified via `integration/verify_ops_e2e.py`.
- Autonomy/sync profile definitions are tracked under `profiles/autonomy/`.
- Device capability profiles are defined under `profiles/`.
- Python modules under `devices/` remain host-side simulation and verification harnesses.
- Native profile-to-runtime mapping can be checked via `arduino/verify_native_layout.py`.
- Build and toolchain guidance is documented in `docs/build.md`.
- UART framing baseline is documented in `docs/uart-internal-transport.md`.
- UART retry + sequence rollover verifier is available under `common/transport/verify_uart_sync_retry.py`.
- RPi-Only refactor v1.00.00 — internal controllers deprecated

## Workspace Layout

- `common/` - shared protocol, transport, queue, and platform modules.
- `arduino/` - shared Arduino C++ runtime helpers.
- `profiles/` - normalized device profile JSON files.
- `devices/` - per-device implementation roots.
- `integration/` - cross-device/server integration verifiers.
- `docs/` - firmware process and build documentation.

## Device Families Covered

- ESP32-S3 USB-OTG (`esp32_service`) (DEPRECATED in v1.00.00)
- M5Stamp S3 (`m5stamp_s3`) (DEPRECATED in v1.00.00)
- Atom S3 (`atom_s3`) (DEPRECATED in v1.00.00)
- M5Tab (`m5tab`) (DEPRECATED in v1.00.00)
- M5Cardputer console (`m5cardputer_console`) (DEPRECATED in v1.00.00)
- M5Cardputer client (`m5cardputer_client`)
- M5Cardputer Adv (`m5cardputer_adv`)
- M5StickC Plus 2 (`m5stickc_plus2`)
- T-Embed CC1101 (`t_embed_cc1101`)
- Flipper Zero (`flipper_zero`)

## Engineering Rules

- Keep behavior realistic for each hardware profile.
- Do not promise storage-heavy offline features without real storage.
- Keep Raspberry Pi as the single main server.
- Prefer resilient, defensive handling of disconnects and partial failures.
