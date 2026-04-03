# M5Cardputer Client

External handheld firmware target for M5Cardputer/M5Cardputer Adv profiles.

`v0.11.01` implements profile split/shared-base alignment.

`v0.11.02` implements external handheld client MVP flow.

Native Arduino runtimes are available in `m5cardputer_client.ino` and `m5cardputer_adv.ino`.
Preset defaults live in `../../arduino/presets/m5cardputer_client_preset.h` and `../../arduino/presets/m5cardputer_adv_preset.h`.

Native write actions are opt-in via macros (`LC_CHAT_SEND_ENABLED`, `LC_SUPPORT_CREATE_ENABLED`).
`LC_PREFERRED_CHAT_ID` can be used to pin chat send target in constrained deployments.

## Scope

- split built-in console (`m5cardputer_console`) and external handheld target;
- keep `m5cardputer_client` and `m5cardputer_adv` on shared codebase;
- run text-first handheld flow: login, chat list/history/send, blog list/get.

## Files

- `config.py` - handheld client baseline config.
- `models.py` - variant and connection-state models.
- `profile_variants.py` - loader for client/adv profile variants.
- `command_map.py` - planned auth/chat/blog endpoint map for handheld runtime.
- `verify_alignment.py` - profile + command-map alignment verification.
- `ui/*` - handheld runtime controller and session models.
- `ui/verify_flow.py` - external client MVP verification.

## Verification

Run from project root:

```bash
python -m firmware.devices.m5cardputer_client.verify_alignment
python -m firmware.devices.m5cardputer_client.ui.verify_flow
```

Python modules in this directory remain as host-side simulation and verification harnesses.
Profile metadata lists harness files under `host_harness_entries`.
