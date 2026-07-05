# Autonomy Matrix

This document defines realistic autonomy posture for each firmware device profile.

Stage reference: `v0.15.04`.

## Rules Applied

- Raspberry Pi remains the only main server.
- Hardware clients do not get guest flow.
- Devices without storage do not claim deep offline history.
- Sync behavior is constrained by real transport and memory limits.

## Device-Level Matrix

| Device Profile | Autonomy Profile | Offline Scope | Sync Scope | Hard Limits |
| --- | --- | --- | --- | --- |
| `esp32_service` | `service_assist_only` | short telemetry/watchdog buffer | heartbeat + telemetry on reconnect | not a server, no long-term log storage |
| `m5stamp_s3` | `non_autonomous` | local status/alert only | no durable queue | no standalone client/server role |
| `atom_s3` | `non_autonomous` | local status/alert only | no durable queue | no media and no deep UI flow |
| `m5tab` | `control_panel_only` | show last known state, prepare operator intent | state refresh and small intent replay | cannot replace backend/admin APIs |
| `m5cardputer_console` | `limited_text_first` | short text draft/cache only | incremental text sync | no deep media/files without confirmed storage |
| `m5cardputer_client` | `limited_text_first` | short text draft/cache only | incremental text sync | no server replacement behavior |
| `m5cardputer_adv` | `limited_text_first` | short text draft/cache only | incremental text sync | same limits as shared client profile |
| `m5stickc_plus2` | `non_autonomous_text_first` | text UI snapshot only | refresh on reconnect | no offline delivery queue |
| `t_embed_cc1101` | `limited_buffered` | buffered text/template window | incremental sync with constrained transport fallback | no heavy media streams |
| `flipper_zero` | `non_autonomous_limited` | local utilities/capability detection | network sync only when external network module exists | no network claims without Wi-Fi board |

## Autonomy Profile Source

Canonical autonomy definitions are stored in:

- `firmware/profiles/autonomy/*.json`

Validation script:

```bash
python firmware/profiles/autonomy/verify_profiles.py
```

## Pending Hardware Confirmation

These files define software contract and expected behavior.
Real battery/runtime and field-network characteristics still require hardware-level validation runs.
