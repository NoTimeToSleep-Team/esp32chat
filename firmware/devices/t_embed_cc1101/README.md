# T-Embed CC1101

Text-first handheld client firmware target.

Shell/login MVP implemented in `v0.13.01`.

Client MVP implemented in `v0.13.02`.

Native Arduino runtime is available in `t_embed_cc1101.ino`.
Preset defaults live in `../../arduino/presets/t_embed_cc1101_preset.h`.

Native write actions are opt-in via macros (`LC_CHAT_SEND_ENABLED`, `LC_SUPPORT_CREATE_ENABLED`).
`LC_PREFERRED_CHAT_ID` can be used to pin chat send target in constrained deployments.

## Scope

- secure login flow with `client_kind=device`;
- session validation and logout through auth API;
- baseline navigation state (`home/chat/blog/templates/buffer`) for text-first UX.
- text-first client flow: chat list/history/send, blog list/get, local templates and local buffer flush.

## Files

- `config.py` - handheld client baseline config.
- `models.py` - shell/session/navigation models.
- `command_map.py` - allowed auth/mode endpoints.
- `server_api.py` - auth gateway and sender abstraction.
- `shell.py` - shell connection and secure login lifecycle.
- `controller.py` - shell/navigation orchestration.
- `verify_mvp.py` - local shell/login verification against `TestClient`.
- `ui/*` - text-first client runtime modules.
- `ui/verify_flow.py` - local client MVP verification with template and buffer flow.

## Verification

Run from project root:

```bash
python -m firmware.devices.t_embed_cc1101.verify_mvp
python -m firmware.devices.t_embed_cc1101.ui.verify_flow
```

Python modules in this directory remain as host-side simulation and verification harnesses.
Profile metadata lists harness files under `host_harness_entries`.
