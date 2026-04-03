# Native Runtime Map

This map links each device profile to native runtime files and host harness verifiers.

| profile_id | native runtime | preset/manifest | host harness |
| --- | --- | --- | --- |
| `esp32_service` | `devices/esp32_service/esp32_service.ino` | `arduino/presets/esp32_service_preset.h` | `verify_mvp.py`, `verify_registration_e2e.py` |
| `m5stamp_s3` | `devices/m5stamp/m5stamp_s3.ino` | `arduino/presets/m5stamp_s3_preset.h` | `verify_mvp.py` |
| `atom_s3` | `devices/atom_s3/atom_s3.ino` | `arduino/presets/atom_s3_preset.h` | `verify_mvp.py` |
| `m5tab` | `devices/m5tab/m5tab.ino` | `arduino/presets/m5tab_preset.h` | `verify_mvp.py`, `admin_users/verify_flow.py`, `admin_ops/verify_flow.py` |
| `m5cardputer_console` | `devices/m5cardputer_console/m5cardputer_console.ino` | `arduino/presets/m5cardputer_console_preset.h` | `verify_mvp.py`, `chat/verify_flow.py`, `blog/verify_flow.py`, `service_actions/verify_flow.py` |
| `m5cardputer_client` | `devices/m5cardputer_client/m5cardputer_client.ino` | `arduino/presets/m5cardputer_client_preset.h` | `verify_alignment.py`, `ui/verify_flow.py` |
| `m5cardputer_adv` | `devices/m5cardputer_client/m5cardputer_adv.ino` | `arduino/presets/m5cardputer_adv_preset.h` | `verify_alignment.py`, `ui/verify_flow.py` |
| `m5stickc_plus2` | `devices/m5stickc_plus2/m5stickc_plus2.ino` | `arduino/presets/m5stickc_plus2_preset.h` | `verify_mvp.py`, `ui/verify_flow.py` |
| `t_embed_cc1101` | `devices/t_embed_cc1101/t_embed_cc1101.ino` | `arduino/presets/t_embed_cc1101_preset.h` | `verify_mvp.py`, `ui/verify_flow.py` |
| `flipper_zero` | `devices/flipper_zero/fap/local_chat_flipper.c` | `devices/flipper_zero/fap/application.fam` | `verify_mvp.py`, `ui/verify_flow.py` |

The canonical source remains profile metadata in `firmware/profiles/*.json`.
