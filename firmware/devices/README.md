# Firmware Devices

Per-device implementation roots.

Each folder defines one firmware target family.

Current status:

- `esp32_service/` has MVP baseline implemented in `v0.08.01` and registration/telemetry e2e verifier in `v0.15.01`.
- `m5stamp/` has MVP baseline implemented in `v0.08.02`.
- `atom_s3/` has MVP baseline implemented in `v0.08.03`.
- `m5tab/` has shell/info + admin-users + admin-ops MVP implemented up to `v0.09.03`.
- `m5cardputer_console/` has shell/login + chat + blog/service shortcuts MVP implemented up to `v0.10.03`.
- `m5cardputer_client/` has profile split + external client MVP implemented up to `v0.11.02`.
- `m5stickc_plus2/` has shell/login + compact client MVP implemented up to `v0.12.02`.
- `t_embed_cc1101/` has shell/login + text-first client MVP implemented up to `v0.13.02`.
- `flipper_zero/` has shell/capability-detection + limited client MVP implemented up to `v0.14.02`.
- other targets remain staged placeholders for later substages.
