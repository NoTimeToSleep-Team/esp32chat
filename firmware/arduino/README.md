# Arduino Runtime

This directory contains shared C++ helpers for ESP32/M5 `.ino` firmware targets.

## Shared Files

- `common/local_chat_runtime.h` - Wi-Fi, HTTP, auth, ops heartbeat, chat/blog/support probes, and optional write actions.
- `presets/runtime_profiles.h` - helper builders for service/client runtime profiles.

## Device Presets

- `presets/esp32_service_preset.h`
- `presets/m5stamp_s3_preset.h`
- `presets/atom_s3_preset.h`
- `presets/m5tab_preset.h`
- `presets/m5cardputer_console_preset.h`
- `presets/m5cardputer_client_preset.h`
- `presets/m5cardputer_adv_preset.h`
- `presets/m5stickc_plus2_preset.h`
- `presets/t_embed_cc1101_preset.h`

## Device Sketch Mapping

- `devices/esp32_service/esp32_service.ino`
- `devices/m5stamp/m5stamp_s3.ino`
- `devices/atom_s3/atom_s3.ino`
- `devices/m5tab/m5tab.ino`
- `devices/m5cardputer_console/m5cardputer_console.ino`
- `devices/m5cardputer_client/m5cardputer_client.ino`
- `devices/m5cardputer_client/m5cardputer_adv.ino`
- `devices/m5stickc_plus2/m5stickc_plus2.ino`
- `devices/t_embed_cc1101/t_embed_cc1101.ino`

Each sketch can be opened directly in Arduino IDE and built per board profile.
Sketches now stay minimal (`setup/loop`) while per-device defaults are centralized in preset headers.

## Runtime Control Macros

Common macros used by sketches:

- `LC_WIFI_SSID`
- `LC_WIFI_PASSWORD`
- `LC_SERVER_BASE_URL`
- `LC_LOGIN`
- `LC_PASSWORD`
- `LC_OPS_SESSION_TOKEN` (service-node profiles)

Optional write-action macros are disabled by default and must be explicitly enabled:

- `LC_CHAT_SEND_ENABLED`
- `LC_SUPPORT_CREATE_ENABLED`
- `LC_ADMIN_REPLY_ENABLED`
- `LC_ADMIN_RESOLVE_ENABLED`
- `LC_ADMIN_BLOG_PUBLISH_ENABLED`

Optional targeting macros:

- `LC_PREFERRED_CHAT_ID`
- `LC_ADMIN_TICKET_ID`

Runtime behavior for enabled actions is one-shot per boot cycle.

This keeps default behavior non-destructive while preserving native runtime paths for chat/support/admin actions.

## Layout Validation

Run from project root:

```bash
python firmware/arduino/verify_native_layout.py
```

It checks runtime/preset/manifest integrity and host harness file mappings from profile metadata.
Harness entries are restricted to Python verify-oriented files (`*verify*.py`).
