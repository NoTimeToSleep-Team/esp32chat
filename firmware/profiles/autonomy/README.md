# Autonomy Profiles

This directory stores normalized autonomy and sync-profile definitions referenced by `firmware/profiles/*.json` via the `autonomy_profile` key.

Each profile must stay realistic:

- Raspberry Pi remains the single main server;
- no fake deep offline history for devices without storage;
- no guest mode in hardware client flows;
- sync behavior is declared explicitly and scoped by hardware limits.

## Local Verification

Run from project root:

```bash
python firmware/profiles/autonomy/verify_profiles.py
```
