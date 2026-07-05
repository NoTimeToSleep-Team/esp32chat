# M5Tab

Administrative HMI firmware target for local panel workflows.

Implemented shell/info MVP in `v0.09.01`, admin-users flow in `v0.09.02`, and admin-ops flow in `v0.09.03`.

Native Arduino runtime is available in `m5tab.ino`.
Preset defaults live in `../../arduino/presets/m5tab_preset.h`.

Admin write actions in native runtime are opt-in via macros (`LC_ADMIN_REPLY_ENABLED`, `LC_ADMIN_RESOLVE_ENABLED`, `LC_ADMIN_BLOG_PUBLISH_ENABLED`).
Default `m5tab.ino` uses `client_kind=web` for admin-auth parity with server role constraints.
`LC_ADMIN_TICKET_ID` can be used to pin target ticket for reply/status actions.

## Scope

- shell connection state (`disconnected/connecting/connected/degraded`);
- telemetry gateway for information screen data collection;
- information screen presenter where all fields are derived from telemetry endpoints;
- admin users flow: list/get/ban/unban/blacklist/unblacklist/delete via server API;
- admin ops flow: support/blog/RFID actions and admin mode toggle with required hold sequence;
- dedicated admin-users/admin-ops command maps and screen models/presenter/controller.

## Files

- `config.py` - shell configuration.
- `models.py` - shell and info screen models.
- `command_map.py` - allowed telemetry endpoints.
- `server_api.py` - telemetry gateway.
- `screens/info.py` - information screen presenter.
- `screens/admin_users/*` - admin users screen flow modules.
- `screens/admin_ops/*` - admin ops screen flow modules.
- `shell.py` - shell connection lifecycle.
- `controller.py` - shell/info, admin users and admin ops orchestration.
- `verify_mvp.py` - local end-to-end verification against `TestClient`.
- `screens/admin_users/verify_flow.py` - admin users flow verification against `TestClient`.
- `screens/admin_ops/verify_flow.py` - admin ops flow verification against `TestClient`.

## Verification

Run from project root:

```bash
python -m firmware.devices.m5tab.verify_mvp
python -m firmware.devices.m5tab.screens.admin_users.verify_flow
python -m firmware.devices.m5tab.screens.admin_ops.verify_flow
```

Python modules in this directory remain as host-side simulation and verification harnesses.
Profile metadata lists harness files under `host_harness_entries`.
