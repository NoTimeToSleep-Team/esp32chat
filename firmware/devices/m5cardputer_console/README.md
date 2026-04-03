# M5Cardputer Console

Built-in console firmware target for the internal M5Cardputer.

Implemented shell/login MVP in `v0.10.01`, chat MVP in `v0.10.02`, and blog/service shortcuts in `v0.10.03`.

Native Arduino runtime is available in `m5cardputer_console.ino`.
Preset defaults live in `../../arduino/presets/m5cardputer_console_preset.h`.

By default, optional write actions in native runtime are disabled (`LC_CHAT_SEND_ENABLED=0`, `LC_SUPPORT_CREATE_ENABLED=0`).
`LC_PREFERRED_CHAT_ID` can be used to pin chat send target in constrained deployments.

## Scope

- secure login flow with `client_kind=device`;
- session validation and logout through auth API;
- basic text-first navigation state (`home/chat/blog/service`);
- text-first chat flow: list chats, read history, send text;
- blog read flow: list posts and open selected post;
- safe service shortcuts: health/readiness/mode/account-limits read-only checks;
- explicit command maps without guest-login/media paths.

## Files

- `config.py` - console configuration.
- `models.py` - shell/session/navigation models.
- `command_map.py` - allowed auth/mode endpoints for this substage.
- `server_api.py` - auth gateway and command sender abstraction.
- `shell.py` - shell connection and secure login lifecycle.
- `controller.py` - shell/navigation orchestration.
- `verify_mvp.py` - local end-to-end verification against `TestClient`.
- `chat/*` - chat gateway/models/presenter/controller.
- `chat/verify_flow.py` - chat flow verification against `TestClient`.
- `blog/*` - blog read gateway/models/presenter/controller.
- `blog/verify_flow.py` - blog read flow verification against `TestClient`.
- `service_actions/*` - safe shortcuts gateway/models/presenter/controller.
- `service_actions/verify_flow.py` - safe shortcuts verification against `TestClient`.

## Verification

Run from project root:

```bash
python -m firmware.devices.m5cardputer_console.verify_mvp
python -m firmware.devices.m5cardputer_console.chat.verify_flow
python -m firmware.devices.m5cardputer_console.blog.verify_flow
python -m firmware.devices.m5cardputer_console.service_actions.verify_flow
```

Python modules in this directory remain as host-side simulation and verification harnesses.
Profile metadata lists harness files under `host_harness_entries`.
