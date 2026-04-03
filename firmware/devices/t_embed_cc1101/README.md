# T-Embed CC1101

Text-first handheld client firmware target.

Shell/login MVP implemented in `v0.13.01`.

Client MVP implemented in `v0.13.02`.

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
