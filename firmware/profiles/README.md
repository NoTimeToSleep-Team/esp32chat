# Device Profiles

This directory stores normalized capability profiles for each firmware target.

## Profile Format

Each profile file is JSON and includes:

- `profile_id` - stable profile key;
- `device_display_name` - user-facing name;
- `firmware_path` - target implementation folder;
- `category` - internal service, admin panel, console, or client;
- `transports` - practical transport options;
- `capabilities` - explicit feature matrix;
- `autonomy_profile` - realistic offline posture;
- `constraints` - hard engineering limits.
- `preferred_stack` - primary implementation toolchain (Arduino IDE / PlatformIO / ESP-IDF / Flipper SDK).
- `native_runtime_entry` - native firmware runtime file path (`.ino` or `.c`).
- `native_preset_entry` - per-device Arduino preset header path (`*_preset.h`) for Arduino targets.
- `native_manifest_entry` - required native manifest path for targets that use it (Flipper `.fam`).
- `host_harness_entries` - Python verification/simulation files kept for host-side checks.

`v0.07.01` defines baseline profiles used by later implementation stages.

`v0.15.04` adds explicit autonomy definitions under `firmware/profiles/autonomy/`.

## Autonomy Validation (Local)

```bash
python firmware/profiles/autonomy/verify_profiles.py
```
