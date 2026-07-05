# Python Harness Policy

This project now treats device-native runtime and Python runtime as separate concerns.

## Native Runtime

- ESP32/M5 targets run native Arduino sketches (`*.ino`).
- Flipper target runs native `.fap` C source (`*.c` + `.fam`).

## Python Files in `firmware/devices/*`

Python files are kept only for host-side verification/simulation harnesses.
They are not flashed to device firmware.

Examples:

- `verify_mvp.py`
- `verify_flow.py`
- `verify_registration_e2e.py`
- `verify_alignment.py`

## Profile Metadata Contract

Each firmware profile tracks:

- `native_runtime_entry`
- `native_preset_entry` (Arduino targets)
- `native_manifest_entry` (Flipper targets)
- `host_harness_entries` (Python verify-only files)

Validation command:

```bash
python firmware/arduino/verify_native_layout.py
```
