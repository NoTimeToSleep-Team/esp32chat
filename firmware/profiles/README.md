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

`v0.07.01` defines baseline profiles used by later implementation stages.

`v0.15.04` adds explicit autonomy definitions under `firmware/profiles/autonomy/`.

## Autonomy Validation (Local)

```bash
python firmware/profiles/autonomy/verify_profiles.py
```
