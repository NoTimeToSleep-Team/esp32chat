# Firmware Build Guide (Workspace Bootstrap)

This document defines baseline build workflow for the firmware workspace introduced in `v0.07.01`.

## Scope

- Set up toolchains for upcoming device stages.
- Keep build commands explicit and reproducible.
- Avoid claiming executable firmware before implementation substages.

At `v0.07.01`, this workspace contains structure and profiles, not runnable firmware binaries.

## Directory Entry Points

- Shared modules: `firmware/common/`
- Device targets: `firmware/devices/`
- Device profiles: `firmware/profiles/`

## Toolchain Baseline

### ESP32 and M5Stack Families

Supported baseline options:

- ESP-IDF (recommended for low-level control)
- PlatformIO (recommended for multi-target ergonomics)

Install references:

- ESP-IDF docs: official install instructions per host OS.
- PlatformIO core: `pip install platformio`.

### Flipper Zero

Use official Flipper SDK/FBT workflow for app firmware build.

## Planned Target Mapping

- `devices/esp32_service` -> stage `v0.08.01`
- `devices/m5stamp` -> stage `v0.08.02`
- `devices/atom_s3` -> stage `v0.08.03`
- `devices/m5tab` -> stage `v0.09.*`
- `devices/m5cardputer_console` -> stage `v0.10.*`
- `devices/m5cardputer_client` -> stage `v0.11.*`
- `devices/m5stickc_plus2` -> stage `v0.12.*`
- `devices/t_embed_cc1101` -> stage `v0.13.*`
- `devices/flipper_zero` -> stage `v0.14.*`

## Profile Validation (Local)

Before implementing new firmware code, validate profile JSON files:

```bash
python -c "import json, pathlib; [json.loads(p.read_text(encoding='utf-8')) for p in pathlib.Path('firmware/profiles').glob('*.json')]; print('profiles_ok')"
```

## Protocol Contract Validation (Local)

Validate protocol codec coverage against message samples:

```bash
python -m firmware.common.protocol.verify_contract_samples
```

## Transport and Queue Validation (Local)

Validate retry, ACK, duplicate handling, and reconnect sequence:

```bash
python -m firmware.common.transport.verify_transport_queue
```

## ESP32 Service MVP Verification (Local)

Validate command mapping with server APIs and service controller MVP flow:

```bash
python -m firmware.devices.esp32_service.verify_mvp
```

## Device Registration/Telemetry E2E Verification (Local)

Validate integrated register -> heartbeat -> telemetry -> status flow (reference device: `esp32_service`):

```bash
python -m firmware.devices.esp32_service.verify_registration_e2e
```

## Chat Web + Device E2E Verification (Local)

Validate chat message parity between web realtime event and device protocol event mapping:

```bash
python -m firmware.integration.verify_chat_e2e
```

## Blog/Support/Admin Ops E2E Verification (Local)

Validate integrated admin-content and support flow parity across admin + device client paths:

```bash
python -m firmware.integration.verify_ops_e2e
```

## Autonomy Profile Validation (Local)

Validate that every device profile references an existing autonomy definition:

```bash
python firmware/profiles/autonomy/verify_profiles.py
```

## M5Stamp S3 MVP Verification (Local)

Validate heartbeat/indicator/telemetry-hooks/emergency-signals flow and read-only server mapping:

```bash
python -m firmware.devices.m5stamp.verify_mvp
```

## Atom S3 MVP Verification (Local)

Validate status/alert model and safe quick actions flow:

```bash
python -m firmware.devices.atom_s3.verify_mvp
```

## M5Tab Shell/Info MVP Verification (Local)

Validate shell connection and information screen telemetry mapping:

```bash
python -m firmware.devices.m5tab.verify_mvp
```

## M5Tab Admin Users Flow Verification (Local)

Validate M5Tab user-admin flow (list/get/ban/unban/blacklist/unblacklist/delete) through server APIs only:

```bash
python -m firmware.devices.m5tab.screens.admin_users.verify_flow
```

## M5Tab Admin Ops Flow Verification (Local)

Validate admin ops support/blog/RFID/mode safe-sequence flow:

```bash
python -m firmware.devices.m5tab.screens.admin_ops.verify_flow
```

## M5Cardputer Console Shell/Login MVP Verification (Local)

Validate built-in console secure login (`client_kind=device`), session restore/logout, and basic navigation state:

```bash
python -m firmware.devices.m5cardputer_console.verify_mvp
```

## M5Cardputer Console Chat MVP Verification (Local)

Validate text-first chat flow (list chats, load history, send text):

```bash
python -m firmware.devices.m5cardputer_console.chat.verify_flow
```

## M5Cardputer Console Blog Read Verification (Local)

Validate blog list/get flow for console user:

```bash
python -m firmware.devices.m5cardputer_console.blog.verify_flow
```

## M5Cardputer Console Service Shortcuts Verification (Local)

Validate safe read-only shortcuts (health/readiness/mode/account limits):

```bash
python -m firmware.devices.m5cardputer_console.service_actions.verify_flow
```

## M5Cardputer External Profile Alignment Verification (Local)

Validate shared codebase alignment for `m5cardputer_client` + `m5cardputer_adv` profiles and handheld command-map coverage:

```bash
python -m firmware.devices.m5cardputer_client.verify_alignment
```

## M5Cardputer External Client MVP Verification (Local)

Validate handheld login/chat/blog flow (text-first):

```bash
python -m firmware.devices.m5cardputer_client.ui.verify_flow
```

## M5StickC Plus 2 Shell/Login MVP Verification (Local)

Validate compact shell/login flow for M5StickC Plus 2:

```bash
python -m firmware.devices.m5stickc_plus2.verify_mvp
```

## M5StickC Plus 2 Compact Client MVP Verification (Local)

Validate compact text-first chat/blog flow:

```bash
python -m firmware.devices.m5stickc_plus2.ui.verify_flow
```

## T-Embed CC1101 Shell/Login MVP Verification (Local)

Validate text-first shell/login flow for T-Embed CC1101:

```bash
python -m firmware.devices.t_embed_cc1101.verify_mvp
```

## T-Embed CC1101 Client MVP Verification (Local)

Validate text-first chat/blog/templates/local-buffer flow:

```bash
python -m firmware.devices.t_embed_cc1101.ui.verify_flow
```

## Flipper Zero Shell/Capability Detection Verification (Local)

Validate shell startup, Wi-Fi dev board capability detection, and mode split:

```bash
python -m firmware.devices.flipper_zero.verify_mvp
```

## Flipper Zero Limited Client Mode Verification (Local)

Validate lightweight login/chat/blog flow with capability-gated network mode:

```bash
python -m firmware.devices.flipper_zero.ui.verify_flow
```

Flipper-specific capability notes are documented in `firmware/docs/flipper.md`.

## Build Validation Policy

- Mark checks as executed only if run in current environment.
- Hardware flashing and on-device runtime checks are separate from workspace bootstrap.
- If target hardware is unavailable, keep result as "structure verified, hardware run pending".
