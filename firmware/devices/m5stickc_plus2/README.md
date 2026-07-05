# M5StickC Plus 2

Compact handheld client firmware target.

Shell/login MVP implemented in `v0.12.01`.

Compact client MVP implemented in `v0.12.02`.

Native Arduino runtime is available in `m5stickc_plus2.ino`.
Preset defaults live in `../../arduino/presets/m5stickc_plus2_preset.h`.

Optional chat send action is opt-in via `LC_CHAT_SEND_ENABLED`.
`LC_PREFERRED_CHAT_ID` can be used to pin chat send target in constrained deployments.

## Scope

- secure login flow with `client_kind=device`;
- session validation and logout through auth API;
- compact navigation state (`home/chat/blog`) for next substage MVP.
- compact client text-first flow: chat list/history/send and blog list/get.

## Files

- `config.py` - compact client baseline config.
- `models.py` - shell/session/navigation models.
- `command_map.py` - allowed auth/mode endpoints.
- `server_api.py` - auth gateway and sender abstraction.
- `shell.py` - shell connection and secure login lifecycle.
- `controller.py` - shell/navigation orchestration.
- `verify_mvp.py` - local end-to-end verification against `TestClient`.
- `ui/*` - compact client runtime controller and command map.
- `ui/verify_flow.py` - compact client MVP verification against `TestClient`.

## Verification

Run from project root:

```bash
python -m firmware.devices.m5stickc_plus2.verify_mvp
python -m firmware.devices.m5stickc_plus2.ui.verify_flow
```

Python modules in this directory remain as host-side simulation and verification harnesses.
Profile metadata lists harness files under `host_harness_entries`.
